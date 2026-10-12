# SuperLU & Crank-Nicolson PDE Implementation Guide

## 1. What is SuperLU?

SuperLU is a high-performance C library for solving large, sparse, nonsymmetric systems of linear equations:

    A * x = b

It computes a Sparse LU Decomposition with partial pivoting:

    Pr * A * Pc = L * U

Where:
- Pr, Pc: Row and column permutation matrices (stabilizes calculation and minimizes fill-in).
- L: Sparse lower triangular matrix with unit diagonal.
- U: Sparse upper triangular matrix.

In Python, `scipy.sparse.linalg.splu` is the direct C-level binding to SuperLU.

---

## 2. Why SuperLU is Used in AlphaStreams PDE Solver

File Reference: `domains/analytics/domain/services/pde_solver.py`

Option prices are evaluated using the second-order **Crank-Nicolson finite difference scheme**. Crank-Nicolson is a semi-implicit time-stepping method.

At every backward time step `j -> j + 1` (across N = 300 steps):

    A * V^(j+1) = B * V^j + BoundaryTerms

### Algorithmic Complexity Comparison:
1. **Standard Dense Matrix Solver (`numpy.linalg.solve`)**:
   - Inversion cost per step: O(M^3)
   - Total runtime across N steps: O(N * M^3)
   - At M=300, N=300: ~8.1 * 10^9 operations (Too slow for live market pricing).

2. **Pre-factored Sparse SuperLU Solver (`scipy.sparse.linalg.splu`)**:
   - Matrix A is tridiagonal and constant across all time steps.
   - One-time LU factorization outside loop: O(M)
   - Forward/backward substitution per step inside loop: O(M)
   - Total runtime across N steps: O(N * M)
   - At M=300, N=300: ~9.0 * 10^4 operations (~90,000x faster, sub-millisecond execution).

---

## 3. Code Breakdown in `pde_solver.py`

### Step A: CSC Sparse Matrix Construction
Lines 67-68:
```python
# Matrix A (Implicit LHS, time step j+1)
# -alpha on subdiagonal, (1 + beta) on main diagonal, -gamma on superdiagonal
A = diags(
    [-alpha[1:], 1.0 + beta, -gamma[:-1]],
    [-1, 0, 1],
    shape=(self.M - 1, self.M - 1),
    format="csc"
)
```
- Creates a sparse tridiagonal matrix `A` stored in Compressed Sparse Column (CSC) format, required by SuperLU.

### Step B: One-Time SuperLU Factorization
Line 74:
```python
# Pre-factorize Matrix A via SuperLU for O(M) linear time backward steps
A_solver = splu(A)
```
- Performed **once** outside the time-stepping loop.
- Calculates and stores L and U factors in C memory.

### Step C: High-Speed Backward Substitution Loop
Lines 77-94:
```python
for j in range(self.N):
    rhs = B.dot(grid[1:self.M])
    tau_old = j * self.dt
    tau_new = (j + 1) * self.dt

    if self.option_type in ("call", "ce"):
        v_old_top = self.S_max - self.K * np.exp(-self.r * tau_old)
        v_new_top = self.S_max - self.K * np.exp(-self.r * tau_new)
        rhs[-1] += gamma[-1] * (v_old_top + v_new_top)
    else:
        v_old_bottom = self.K * np.exp(-self.r * tau_old)
        v_new_bottom = self.K * np.exp(-self.r * tau_new)
        rhs[0] += alpha[0] * (v_old_bottom + v_new_bottom)

    # Solve linear system in O(M) time via pre-factored SuperLU
    grid[1:self.M] = A_solver.solve(rhs)
```
- In each iteration, `A_solver.solve(rhs)` only executes triangular forward substitution (`L * y = Pr * rhs`) and backward substitution (`U * (Pc^T * x) = y`).
- Entire grid backward propagation finishes in sub-millisecond execution time.
