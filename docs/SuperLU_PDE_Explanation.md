# Crank-Nicolson PDE Pricing and the SuperLU Optimization

How `domains/analytics/domain/services/pde_solver.py` computes a fair option price, what every component (grid, α/β/γ, matrices A and B, boundary term, Rannacher start-up, SuperLU) is, and the performance optimizations around it. Written in layers: start simple, go deeper only as needed.

Worked example used throughout: a NIFTY **24200 call**, spot **24000**, **30 days** to expiry, IV **14%**, r = 6.5%, dividend yield q = 1.2%. All numbers below come from running the repository's own `CrankNicolsonPDE` and `bsm_prices`.

---

## Layer 1: The big idea

Black-Scholes gives a closed-form formula, but the same model can also be written as a partial differential equation (PDE) describing how an option's value changes with the stock price and with time. Crank-Nicolson solves that equation numerically.

The trick is to **start at expiry, where the value is known exactly** (a call is worth `max(S − K, 0)`), then **step backwards in time**, one small step at a time, until today. The value is tracked on a grid of possible stock prices, and at the end it is read off at today's spot price.

**Analogy:** the Black-Scholes PDE is mathematically a heat equation, and Crank and Nicolson invented the method in 1947 for heat flow. The payoff at expiry is a sharp hockey-stick shape. Going back in time, uncertainty smooths it out, like heat spreading along a metal rod. That smoothing *is* the option's time value.

---

## Layer 2: The grid

```
   stock price S
   28,414 ┤ ● ● ● ● ● ● ●   ← top edge: known (deep in the money)
          │ ● ● ● ● ● ● ●
   24,200 ┤ ● ● ● ● ● ● ●   ← strike (node 141 is at 24,188)
   24,000 ┤ ● ● ● ● ● ● ●   ← today's spot, between nodes 133 and 134
          │ ● ● ● ● ● ● ●
   20,440 ┤ ● ● ● ● ● ● ●   ← bottom edge: known (call worthless)
          └─┬─────────────┬─→ time
          today        expiry  ← right column known: max(S−K, 0)
                ◄──────── we step this way
```

| Piece | Code | Example |
|---|---|---|
| Price range | `price_grid`: `[min(S0,K)·e^(−w), max(S0,K)·e^(+w)]`, `w = 4·σ·√T` | 20,440 to 28,414: four standard deviations of the price at expiry beyond both spot and strike |
| Price nodes | `M = 300`, uniform spacing | A node every 26.6 points |
| Time steps | `N = 300`, `dt = T / N` | 300 steps of about 2.4 hours for 30 days |
| Starting column | `np.maximum(S_nodes − K, 0)` | The payoff at expiry |

A 301 × 301 grid: the expiry column and the top and bottom rows are known; the solver fills in the rest column by column, moving left.

**Why this range.** The option's value only changes shape where the stock can plausibly end up. Past four standard deviations there is less than 0.01% probability mass, so the edges can be set from simple formulas without distorting the price near spot. The earlier grid ran from 0 to `max(3K, 2.5·S0)` (72,600 here), which put a node only every 242 points; the new range puts nine times as many nodes where they matter. The width was chosen by measurement over strikes ±10%, 1-60 days and 10-40% volatility: 6 standard deviations gave a worst error of ₹0.43, 4 gave ₹0.19.

---

## Layer 3: One time step, and where A and B come from

### 3a. Each node only talks to its neighbours

The PDE involves the slope and the curvature of the value curve. On a grid they are approximated from a node's two neighbours:

- slope ≈ (value above − value below) / (2·dS)
- curvature ≈ (value above − 2 × this value + value below) / dS²

So a node's new value depends only on itself and the two nodes next to it. That is why the matrices have only three diagonals.

### 3b. The three weights α, β, γ (`operator_coefficients`)

With S_i the price at node i:

```
diffusion = ½·σ²·S_i² / dS²
drift     = ½·(r − q)·S_i / dS

α = ½·dt·(diffusion − drift)      weight on the node BELOW
β = ½·dt·(2·diffusion + r)        weight on the node ITSELF
γ = ½·dt·(diffusion + drift)      weight on the node ABOVE
```

- **diffusion** is volatility spreading value between neighbours. Higher volatility means more spreading (smoothing).
- **drift** is the risk-neutral growth of the stock, at rate r minus the dividend yield q. Dividends paid out slow the stock's growth, so the node above gets slightly more weight than the node below (γ > α), but less than without dividends.
- **+r inside β** is discounting: money later is worth less today.
- The grid no longer starts at 0, so S_i is used directly rather than i·dS.

At node 133 in the example: α = 1.08893, β = 2.18442, γ = 1.09548.

<details>
<summary>Where the weights come from (derivation)</summary>

In time-to-maturity τ the PDE is `∂V/∂τ = ½σ²S²·V_SS + (r − q)·S·V_S − r·V`. Substituting the central differences above, the right-hand side at node i becomes

```
L(V)_i = a·V[i−1] + b·V[i] + c·V[i+1]
a = diffusion − drift,   b = −(2·diffusion + r),   c = diffusion + drift
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
| **Boundary term** | Known edge values moved to the right-hand side | First and last equations |

At node 133:

```
row of A: [ −1.08893   3.18442   −1.09548 ]
row of B: [  1.08893  −1.18442    1.09548 ]
```

They are mirror images (signs flipped, 1+β vs 1−β) because one is the implicit half and the other the explicit half. Note that B's diagonal is negative here: with fine price steps β is larger than 1. The scheme is still stable, but a negative diagonal is what lets the payoff's kink at the strike ring for a few steps. Layer 3e explains the fix.

A is 299×299 = 89,401 entries, of which only **895 are non-zero**, so it is stored as a sparse matrix:

```python
A = diags([-alpha[1:], 1.0 + beta, -gamma[:-1]], [-1, 0, 1],
          shape=(M - 1, M - 1), format="csc")
```

`diags` places the three arrays on the sub-diagonal (−1), main diagonal (0) and super-diagonal (+1). The off-diagonals are one shorter, hence the `[1:]` and `[:-1]` slices. `format="csc"` (compressed sparse column) is the format SuperLU expects.

**Why 299 and not 301?** The bottom node (S_min) and the top node (S_max) are known from the boundary conditions, so only the interior nodes are unknown.

**The boundary term** (`boundary_values`): the first and last interior equations refer to the edge nodes. Their values are known:

| Edge | Call | Put |
|---|---|---|
| Top, S_max | `S_max·e^(−qτ) − K·e^(−rτ)` (deep in the money: stock minus dividends, minus discounted strike) | 0 |
| Bottom, S_min | 0 | `K·e^(−rτ) − S_min·e^(−qτ)` |

They move to the right-hand side: `rhs[-1] += γ·(top_old + top_new)` and `rhs[0] += α·(bottom_old + bottom_new)`.

**Why it must be solved as a system:** every new value depends on its new neighbours, so all 299 unknowns are linked. They cannot be computed one at a time; they are solved simultaneously.

### 3e. Rannacher start-up, the loop and the final answer

The payoff has a kink at the strike. Crank-Nicolson's averaging can make that kink oscillate for the first few steps (the negative diagonal of B above), which shows up as error for short-dated, near-the-money options. The standard fix, **Rannacher smoothing**, replaces the first 2 Crank-Nicolson steps with 4 fully implicit half-steps. Implicit steps damp the kink instead of ringing it; after that the solution is smooth and Crank-Nicolson's second-order accuracy takes over.

```python
implicit = splu(I - h·L)                    # h = dt/2, factorised once
for _ in range(4):                          # Rannacher: 4 implicit half-steps
    grid[1:M] = implicit.solve(grid[1:M] + edges)
A_solver = splu(A)                          # factorise once (Layer 4)
for j in range(N - 2):                      # 298 Crank-Nicolson steps
    rhs = B.dot(grid[1:M])                  # 1. known side
    rhs[0] += ...; rhs[-1] += ...           # 2. add both boundaries
    grid[1:M] = A_solver.solve(rhs)         # 3. solve for the new column
fair_price = np.interp(S0, S_nodes, grid)   # 4. value at today's spot
```

Time value building up at S = 24,000 as the solver moves away from expiry:

| After step | Time to expiry | Value |
|---|---|---|
| 2 (end of Rannacher) | 0.2 days | 0.39 |
| 10 | 1 day | 11.89 |
| 100 | 10 days | 149.80 |
| 300 | 30 days (today) | **339.15** |

Today's spot sits between node 133 (23,975.5, value 327.80) and node 134 (24,002.1, value 340.12); `np.interp` draws a straight line between them to get 339.15.

### 3f. How this compares with the BSM price in the pipeline

The pricing subscriber prices every contract both ways:

| | Price | Why |
|---|---|---|
| BSM with q = 1.2% (`bs_fair_call`) | 339.14 | Closed form, includes the dividend yield |
| Crank-Nicolson (`fair_call`) | **339.15** | Same model solved on the grid, also with q |
| BSM with q = 0 | 350.35 | For reference: what ignoring dividends costs |

The two methods now agree to a paisa. Before the accuracy work the PDE had no dividend term and a coarse grid, so `fair_call` was 349.12: about ₹11 of dividend gap and ₹1 of grid error.

**Measured accuracy** against closed-form BSM over strikes ±10%, 1 to 60 days, volatility 10% to 40%, calls and puts (`tests/unit/test_pde_solver.py`):

| | Worst error | Mean error |
|---|---|---|
| Old grid, no Rannacher | ₹21.20 | ₹0.94 |
| Current solver | **₹0.19** | **₹0.022** |

---

## Layer 4: Optimization 1, SuperLU pre-factorisation

### The problem

Each of the 300 time steps solves `A · V_new = rhs`. The original code called `scipy.sparse.linalg.spsolve(A, rhs)` inside the loop.

### The key observation

A never changes during the loop: it is built only from σ, r, q, the grid and dt, which are fixed for one option. Only the right-hand side changes. `spsolve` throws its work away after every call, so the same preparation was being repeated 300 times.

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

The Rannacher matrix is factorised once in the same way.

### What SuperLU is

SuperLU is a C library for sparse LU factorisation, developed at Lawrence Berkeley National Laboratory (X. Sherry Li, James Demmel and others). It works only on non-zero entries, groups columns with the same non-zero pattern into "supernodes" processed as small dense blocks, chooses a column ordering (SciPy's default is COLAMD) to limit fill-in, and uses partial pivoting for stability. `scipy.sparse.linalg.splu` is SciPy's binding to it, and it expects CSC input.

### Measured result

Median of repeated runs on an Intel i5-12450H, Python 3.11, NumPy 1.26.4, SciPy 1.17.1, current grid. The naive version is the same scheme with `spsolve` inside the loop.

| Grid M = N | spsolve every step | splu once | Reduction | Speed-up |
|---|---|---|---|---|
| 200 | 12.7 ms | 3.5 ms | 72.6% | 3.6× |
| 300 (default) | 23.3 ms | 5.8 ms | **75.0%** | 4.0× |
| 500 | 55.1 ms | 10.8 ms | 80.5% | 5.1× |
| 1000 | 210.2 ms | 50.0 ms | 76.2% | 4.2× |

### Complexity, stated precisely

- Each solve with the factors is **O(M)** because A is tridiagonal (no fill-in), so one option is **O(M·N)**.
- Factorising a tridiagonal matrix is also O(M), so the old code was O(M·N) too. The improvement is a **constant-factor** win: it removes the repeated symbolic analysis, ordering, memory allocation and call overhead.
- It would be an asymptotic win (O(M³) per step down to O(M)) only compared with treating A as a dense matrix.

### Why not LAPACK's tridiagonal solver?

LAPACK's `gttrf`/`gttrs` (the Thomas algorithm with pivoting) was benchmarked as a replacement. It was only about 1.3× faster on the batched system, so SuperLU was kept: the time is now dominated by the Python step loop and the `B.dot` product, not the solve.

---

## Layer 5: Optimization 2, batched pricing across a chain

SuperLU made each option fast. A chain of about 50 strikes means 100 contracts. Pricing them one by one runs 100 separate Python loops of 300 steps each, and at that point the cost is Python overhead, not arithmetic.

### One solve for the whole chain

`price_chain_cn` prices many contracts in a single solve. Each contract keeps its own grid and its own α, β, γ (its own strike and IV), and becomes one **block** of a block-diagonal matrix:

```
        ┌ A₁           ┐
A_big = │    A₂        │     each Aᵢ is a 299×299 tridiagonal block;
        │       ⋱      │     the blocks don't touch, so contracts stay independent
        └          A_C ┘
```

A block-diagonal matrix with tridiagonal blocks is still tridiagonal, just longer (C × 299 rows), so SuperLU factorises it once and each time step is one `B.dot` and one solve for every contract at once. Boundary terms and the final interpolation are vectorised with NumPy. The prices are identical to the single-contract solver (a unit test checks parity), and BSM is vectorised the same way (`bsm_prices`).

Measured, one core: 100 contracts take **605 ms looped vs 202 ms batched (3.0×)**.

### Spread across processes

- Threads do not help: the solver loop is Python code, so the GIL lets only one thread run it at a time. An early version measured 28 contracts/s with threads vs 66 sequential.
- The subscriber uses a `ProcessPoolExecutor` via `loop.run_in_executor`. Each process has its own interpreter and GIL.
- The chain is split into one chunk per worker (at least 16 contracts each), and each chunk is one batched solve.
- The pool uses the **spawn** start method because it is created inside a running event loop with open Redis connections, and forking that state into child processes is unsafe.
- Pool size comes from `PRICING_WORKERS` (default: CPU count − 1; compose sets 2).

End-to-end throughput of `OptionsPricingSubscriber.process_event` on a 100-contract chain (CN and BSM for every contract):

| Workers | Before batching | Batched |
|---|---|---|
| 1 | 66 contracts/s | **527 contracts/s** |
| 2 | not measured | **975 contracts/s** |
| 4 | 560 contracts/s | **1,291 contracts/s** |

---

## Layer 6: Scripts for explaining it

### 30 seconds

> "Crank-Nicolson solves the Black-Scholes equation on a grid. I start from the payoff at expiry and step backwards 300 times to today. Each step is a system of equations, A · V_new = B · V_old, where A and B are tridiagonal because each price node only interacts with its two neighbours. CN averages the explicit and implicit methods, so it's stable and second-order accurate. The grid covers four standard deviations around spot and strike, and the first steps are fully implicit to smooth the payoff's kink, so it matches the closed form to within 19 paise across the chain. Since A never changes between steps, I factorise it once with SuperLU, and I stack a whole chain into one block-diagonal system so 100 contracts are one solve."

### 2 minutes, on a whiteboard

1. Draw the grid: price going up, time going left from expiry. Mark the known payoff column and the known edges, four standard deviations out.
2. Circle one node and its two neighbours: each node only talks to these two, which gives three weights: α below, β itself, γ above.
3. Write `A · V_new = B · V_old + boundary`: A is the implicit half, B the explicit half; Crank-Nicolson is the average.
4. Draw the tridiagonal shape: 299×299 with only 895 non-zeros, so it is stored sparse.
5. Accuracy: dividends in the drift, a tight grid, and Rannacher's implicit start-up steps.
6. Speed: A is constant across all steps, so do A = LU once with SuperLU; stack the chain's matrices into one block-diagonal system; split it across processes.
7. Finish: interpolate at today's spot; it matches Black-Scholes to a paisa in the worked example.

---

## Common follow-up questions

| Question | Answer |
|---|---|
| Why not invert A? | The inverse of a tridiagonal matrix is dense: more memory, slower, less accurate. Factorise, never invert. |
| Why not the explicit method? It has no matrix. | It is only stable for very small time steps. CN is stable for any step. |
| Why not the Thomas algorithm? | Thomas is the special-case solver for tridiagonal systems, also O(M). LAPACK's version was measured at only 1.3× faster than SuperLU here, because the solve is no longer the bottleneck. |
| Where does the error come from? | Grid spacing (26.6 points), straight-line interpolation at spot and the approximate edge values. Worst case ₹0.19 over the test range. |
| Any weakness of CN? | The kink in the payoff at the strike causes oscillations near expiry. The solver uses Rannacher smoothing (fully implicit start-up steps) to remove them. |
| Can it price American options? | Not currently; it prices European options. Early exercise would be one extra line per step: `V = max(V, payoff)`. |
| Why use it if Black-Scholes exists? | It is the general method: American exercise, barriers or price-dependent volatility are small changes to the solver, which the formula cannot handle. In this system it also cross-checks the formula. |
| Why one matrix for many contracts? | Python's per-step overhead dominated. One block-diagonal system turns 100 loops into one, and the blocks never interact, so the prices are unchanged. |

Avoid two common overstatements: Crank-Nicolson does **not** need a CFL stability check, and the SuperLU change did **not** reduce complexity from O(M³); it is a constant-factor speed-up over re-solving a sparse tridiagonal system every step.
