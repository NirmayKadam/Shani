# Crank-Nicolson PDE Pricing and the SuperLU Optimization

How `domains/analytics/domain/services/pde_solver.py` computes a fair option price, what every component (grid, α/β/γ, matrices A and B, boundary term, SuperLU) is, and the two performance optimizations around it. Written in layers: start simple, go deeper only as needed.

Worked example used throughout: a NIFTY **24200 call**, spot **24000**, **30 days** to expiry, IV **14%**, r = 6.5%. All numbers below come from running the repository's own `CrankNicolsonPDE` and `BlackScholesMerton` classes.

---

## Layer 1: The big idea

Black-Scholes gives a closed-form formula, but the same model can also be written as a partial differential equation (PDE) describing how an option's value changes with the stock price and with time. Crank-Nicolson solves that equation numerically.

The trick is to **start at expiry, where the value is known exactly** (a call is worth `max(S − K, 0)`), then **step backwards in time**, one small step at a time, until today. The value is tracked on a grid of possible stock prices, and at the end it is read off at today's spot price.

**Analogy:** the Black-Scholes PDE is mathematically a heat equation, and Crank and Nicolson invented the method in 1947 for heat flow. The payoff at expiry is a sharp hockey-stick shape. Going back in time, uncertainty smooths it out, like heat spreading along a metal rod. That smoothing *is* the option's time value.

---

## Layer 2: The grid

```
   stock price S
   72,600 ┤ ● ● ● ● ● ● ●   ← top edge: known (deep in the money)
          │ ● ● ● ● ● ● ●
   24,200 ┤ ● ● ● ● ● ● ●   ← strike
   23,958 ┤ ● ● ● ● ● ● ●   ← today's spot (24,000) is about here
          │ ● ● ● ● ● ● ●
        0 ┤ ● ● ● ● ● ● ●   ← bottom edge: known (call worthless)
          └─┬─────────────┬─→ time
          today        expiry  ← right column known: max(S−K, 0)
                ◄──────── we step this way
```

| Piece | Code | Example |
|---|---|---|
| Top of the price range | `S_max = max(3K, 2.5·S0)` | 72,600. Far enough away that the edge doesn't distort prices near spot |
| Price nodes | `M = 300`, `dS = S_max / M` | A node every 242 points |
| Time steps | `N = 300`, `dt = T / N` | 300 steps of about 2.4 hours for 30 days |
| Starting column | `np.maximum(S_nodes − K, 0)` | The payoff at expiry |

A 301 × 301 grid: the expiry column and the top and bottom rows are known; the solver fills in the rest column by column, moving left.

---

## Layer 3: One time step, and where A and B come from

### 3a. Each node only talks to its neighbours

The PDE involves the slope and the curvature of the value curve. On a grid they are approximated from a node's two neighbours:

- slope ≈ (value above − value below) / (2·dS)
- curvature ≈ (value above − 2 × this value + value below) / dS²

So a node's new value depends only on itself and the two nodes next to it. That is why the matrices have only three diagonals.

### 3b. The three weights α, β, γ (code lines 63-65)

```
α = ¼·dt·(σ²i² − r·i)     weight on the node BELOW
β = ½·dt·(σ²i² + r)       weight on the node ITSELF
γ = ¼·dt·(σ²i² + r·i)     weight on the node ABOVE
```

- **σ²i²** is volatility spreading value between neighbours. Higher volatility means more spreading (smoothing).
- **r·i** is the drift. The risk-neutral stock drifts upward at rate r, so the node above gets slightly more weight than the node below (γ > α).
- **+r inside β** is discounting: money later is worth less today.
- `i` appears instead of S because S = i·dS, and the dS terms cancel out.

At node 99 in the example: α = 0.01272, β = 0.02632, γ = 0.01360.

<details>
<summary>Where the weights come from (derivation)</summary>

In time-to-maturity τ the PDE is `∂V/∂τ = ½σ²S²·V_SS + r·S·V_S − r·V`. Substituting S = i·dS and the central differences above, the right-hand side at node i becomes

```
L(V)_i = a·V[i−1] + b·V[i] + c·V[i+1]
a = ½(σ²i² − r·i),   b = −(σ²i² + r),   c = ½(σ²i² + r·i)
```

Crank-Nicolson averages the new and old time levels:
`(V_new − V_old)/dt = ½·L(V_new) + ½·L(V_old)`.
Multiplying by dt and moving unknowns to the left gives the rows of A and B below, with α = ½·dt·a, β = −½·dt·b, γ = ½·dt·c.
</details>

### 3c. Explicit vs implicit, and why Crank-Nicolson is the average

| Method | Idea | Problem |
|---|---|---|
| Explicit | New value = formula using **old** neighbours. No equations to solve. | Unstable unless dt is tiny (roughly dt ≤ dS²/(σ²S_max²)): errors blow up |
| Implicit | New value defined using **new** neighbours, also unknown. All nodes solved together. | Stable, but only first-order accurate in time |
| Crank-Nicolson | Average of the two: half old, half new | Stable for any step size **and** second-order accurate |

Because Crank-Nicolson is unconditionally stable for this equation, the solver needs no stability (CFL) check.

### 3d. That average is literally A and B

Writing the CN equation for one node, with the new (unknown) values on the left and the old (known) values on the right:

```
 −α·V_new[i−1] + (1+β)·V_new[i] − γ·V_new[i+1]   =   α·V_old[i−1] + (1−β)·V_old[i] + γ·V_old[i+1]
 └──────────── unknown (new step) ────────────┘      └──────────── known (previous step) ───────┘
```

Stacking this for all 299 interior nodes:

```
A · V_new  =  B · V_old  +  boundary term
```

| Component | What it is | Shape and contents |
|---|---|---|
| **A** | Implicit side, multiplies the unknown new values | 299×299 tridiagonal: `−α` below the diagonal, `1+β` on it, `−γ` above it |
| **B** | Explicit side, multiplies the known old values | 299×299 tridiagonal: `α`, `1−β`, `γ` |
| **V_old** | Column computed in the previous step (the payoff at the start) | 299 numbers |
| **V_new** | Column being computed | 299 unknowns |
| **rhs** | `B · V_old` plus the boundary term | 299 known numbers |
| **Boundary term** | Known edge values moved to the right-hand side | Only the last equation (call) or first equation (put) |

At node 99:

```
row of A: [ −0.01272   1.02632   −0.01360 ]
row of B: [  0.01272   0.97368    0.01360 ]
```

They are mirror images (signs flipped, 1+β vs 1−β) because one is the implicit half and the other the explicit half.

A is 299×299 = 89,401 entries, of which only **895 are non-zero**, so it is stored as a sparse matrix:

```python
A = diags([-alpha[1:], 1.0 + beta, -gamma[:-1]], [-1, 0, 1],
          shape=(M - 1, M - 1), format="csc")
```

`diags` places the three arrays on the sub-diagonal (−1), main diagonal (0) and super-diagonal (+1). The off-diagonals are one shorter, hence the `[1:]` and `[:-1]` slices. `format="csc"` (compressed sparse column) is the format SuperLU expects.

**Why 299 and not 301?** The bottom node (S = 0) and the top node (S = S_max) are known from the boundary conditions, so only the interior nodes are unknown.

**The boundary term** (code lines 82-91): the last interior node's equation refers to the top edge node. For a call that value is known, `S_max − K·e^(−rτ)` (deep in the money), so it moves to the right-hand side: `rhs[-1] += γ·(top_old + top_new)`. For a put the known edge is the bottom one, `K·e^(−rτ)` at S = 0: `rhs[0] += α·(bottom_old + bottom_new)`.

**Why it must be solved as a system:** every new value depends on its new neighbours, so all 299 unknowns are linked. They cannot be computed one at a time; they are solved simultaneously.

### 3e. The loop and the final answer

```python
A_solver = splu(A)                          # factorise once (Layer 4)
for j in range(N):                          # 300 steps, expiry → today
    rhs = B.dot(grid[1:M])                  # 1. known side
    rhs[-1] += gamma[-1] * (...)            # 2. add boundary (call)
    grid[1:M] = A_solver.solve(rhs)         # 3. solve for the new column
fair_price = np.interp(S0, S_nodes, grid)   # 4. value at today's spot
```

Time value building up at S = 24,000 as the solver moves away from expiry:

| After step | Time to expiry | Value |
|---|---|---|
| 1 | 0.1 days | 1.21 |
| 10 | 1 day | 14.74 |
| 100 | 10 days | 151.06 |
| 300 | 30 days (today) | **349.12** |

Today's spot sits between node 99 (23,958, value 327.67) and node 100 (24,200, value 451.27); `np.interp` draws a straight line between them to get 349.12. Black-Scholes gives 350.35 for the same inputs without dividends. The ₹1.2 gap is grid error.

### 3f. How this compares with the BSM price in the pipeline

`options_subscriber._solve_strike_sync` prices every strike both ways:

| | Price | Why |
|---|---|---|
| BSM with q = 1.2% (`bs_fair_call`) | 339.14 | Includes the dividend yield |
| BSM with q = 0 | 350.35 | Same formula without dividends |
| Crank-Nicolson (`fair_call`) | 349.12 | The PDE solver has no dividend term |

About ₹11 of the gap between `fair_call` and `bs_fair_call` is the dividend; about ₹1 is grid error.

---

## Layer 4: Optimization 1, SuperLU pre-factorisation

### The problem

Each of the 300 time steps solves `A · V_new = rhs`. The original code called `scipy.sparse.linalg.spsolve(A, rhs)` inside the loop.

### The key observation

A never changes during the loop: it is built only from σ, r, dS and dt, which are fixed for one option. Only the right-hand side changes. `spsolve` throws its work away after every call, so the same preparation was being repeated 300 times.

### What LU factorisation is

Solving a linear system has an expensive part that depends only on A and a cheap part that depends on the right-hand side. LU factorisation does the expensive part once:

```
Pr · A · Pc = L · U      L lower-triangular, U upper-triangular, Pr/Pc row/column permutations
```

After that, each new right-hand side needs two quick sweeps:

1. Forward substitution: solve `L · y = rhs`, top to bottom.
2. Back substitution: solve `U · x = y`, bottom to top.

Analogy: setting up a production line once (expensive), then running each new batch through it quickly.

### The change

```python
# Before: 300 full solves
for j in range(N):
    grid[1:M] = spsolve(A, rhs)        # analyse + order + factorise + solve, every step

# After: factorise once, then reuse
A_solver = splu(A)                      # SuperLU factorisation, once
for j in range(N):
    grid[1:M] = A_solver.solve(rhs)     # forward + back substitution only
```

### What SuperLU is

SuperLU is a C library for sparse LU factorisation, developed at Lawrence Berkeley National Laboratory (X. Sherry Li, James Demmel and others). It works only on non-zero entries, groups columns with the same non-zero pattern into "supernodes" processed as small dense blocks, chooses a column ordering (SciPy's default is COLAMD) to limit fill-in, and uses partial pivoting for stability. `scipy.sparse.linalg.splu` is SciPy's binding to it, and it expects CSC input.

### Measured result

Median of repeated runs on an Intel i5-12450H, Python 3.11, NumPy 1.26.4, SciPy 1.17.1. The naive version is the identical scheme with `spsolve` inside the loop; both return identical prices.

| Grid M = N | spsolve every step | splu once | Reduction | Speed-up |
|---|---|---|---|---|
| 200 | 35.1 ms | 9.2 ms | 73.9% | 3.8× |
| 300 (default) | 64.8 ms | 14.9 ms | **77.0%** | 4.3× |
| 500 | 154.1 ms | 27.5 ms | 82.2% | 5.6× |
| 1000 | 318.3 ms | 23.4 ms | 92.7% | 13.6× |

The gain grows with grid size because the repeated preparation is the expensive part, and the old code did it N times.

### Complexity, stated precisely

- Each solve with the factors is **O(M)** because A is tridiagonal (no fill-in), so one option is **O(M·N)**.
- Factorising a tridiagonal matrix is also O(M), so the old code was O(M·N) too. The improvement is a **constant-factor** win: it removes the repeated symbolic analysis, ordering, memory allocation and call overhead.
- It would be an asymptotic win (O(M³) per step down to O(M)) only compared with treating A as a dense matrix.

---

## Layer 5: Optimization 2, process pool across a chain

SuperLU made each option faster. A chain of about 50 strikes means 100 contracts, each priced by `_solve_strike_sync` (two CN solves and two BSM evaluations per strike).

- The subscriber originally used `asyncio.to_thread`. Threads did not help: the solver loop is Python code, so the GIL lets only one thread run Python at a time. Measured: **28 contracts/s with threads vs 66 sequential**.
- It now uses a `ProcessPoolExecutor` via `loop.run_in_executor`. Each process has its own interpreter and GIL, so strikes are priced in parallel. Measured: **about 560 contracts/s with 4 workers**, roughly 20× the threaded version.
- The pool uses the **spawn** start method because it is created inside a running event loop with open Redis connections, and forking that state into child processes is unsafe.
- Pool size comes from `PRICING_WORKERS` (default: CPU count − 1).

---

## Layer 6: Scripts for explaining it

### 30 seconds

> "Crank-Nicolson solves the Black-Scholes equation on a grid. I start from the payoff at expiry and step backwards 300 times to today. Each step is a system of equations, A · V_new = B · V_old, where A and B are tridiagonal because each price node only interacts with its two neighbours. CN averages the explicit and implicit methods, so it's stable and second-order accurate. Since A never changes between steps, I factorise it once with SuperLU instead of solving from scratch each step. That cut solve time by 77% at our default grid, with identical prices."

### 2 minutes, on a whiteboard

1. Draw the grid: price going up, time going left from expiry. Mark the known payoff column and the known edges.
2. Circle one node and its two neighbours: each node only talks to these two, which gives three weights: α below, β itself, γ above.
3. Write `A · V_new = B · V_old + boundary`: A is the implicit half, B the explicit half; Crank-Nicolson is the average.
4. Draw the tridiagonal shape: 299×299 with only 895 non-zeros, so it is stored sparse.
5. Optimization: A is constant across all 300 steps, so do A = LU once with SuperLU; each step is then just forward and back substitution.
6. Finish: interpolate at today's spot; it matches Black-Scholes to about a rupee.

---

## Common follow-up questions

| Question | Answer |
|---|---|
| Why not invert A? | The inverse of a tridiagonal matrix is dense: more memory, slower, less accurate. Factorise, never invert. |
| Why not the explicit method? It has no matrix. | It is only stable for very small time steps. CN is stable for any step. |
| Why not the Thomas algorithm? | Thomas is the special-case solver for tridiagonal systems, also O(M), and would work here (A is diagonally dominant, so no pivoting is needed). `splu` is the general tool and keeps working if the matrix structure changes. |
| Where does the error come from? | Grid spacing (242 points) and straight-line interpolation: 349.12 vs 350.35. Finer grids reduce it at higher cost. |
| Any weakness of CN? | The kink in the payoff at the strike can cause small oscillations near expiry. The fix is a few fully-implicit start-up steps (Rannacher smoothing). |
| Can it price American options? | Not currently; it prices European options. Early exercise would be one extra line per step: `V = max(V, payoff)`. |
| Why use it if Black-Scholes exists? | It is the general method: American exercise, barriers or price-dependent volatility are small changes to the solver, which the formula cannot handle. In this system it also cross-checks the formula. |
| Why doesn't it match BSM exactly in the pipeline? | The PDE ignores the dividend yield while the BSM code includes it (about ₹11 here), plus about ₹1 of grid error. |

Avoid two common overstatements: Crank-Nicolson does **not** need a CFL stability check, and the SuperLU change did **not** reduce complexity from O(M³); it is a constant-factor speed-up over re-solving a sparse tridiagonal system every step.
