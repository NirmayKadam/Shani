"""
File Overview: Implementation of the Crank-Nicolson Partial Differential Equation (PDE) solver for option pricing.
Provides unconditional numerical stability and O(M) tridiagonal sparse solving via SuperLU pre-factorization.
Domain Service layer (Pure financial mathematics).

Accuracy design:
- Continuous dividend yield q in the drift (r - q), matching the closed-form Black-Scholes-Merton.
- The price grid spans [S_min, S_max] = [min(S0, K) e^{-w}, max(S0, K) e^{+w}] with w = k * sigma * sqrt(T)
  standard deviations (k = 4), instead of [0, 3K]. Nodes sit where the option value actually
  changes, so dS is far smaller for the same M (most visible for short-dated options).
- Rannacher start-up: the first time steps use fully implicit half-steps, which damp the
  oscillations Crank-Nicolson produces from the payoff's kink at the strike.
"""

from typing import Optional
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import splu

# Grid half-width in standard deviations of log-price at expiry, beyond both spot and strike.
# Measured over strikes +-10%, 1-60 days, 10-40% vol: 6 sd -> max error 0.43, 4 sd -> 0.19,
# 3 sd -> 0.08 (finer nodes win). 4 keeps < 0.01% of probability mass past each edge, where
# the Dirichlet values are asymptotic approximations.
_GRID_STD_DEVS = 4.0
# Minimum grid half-width in log-price (keeps a usable grid when sigma*sqrt(T) is tiny)
_MIN_LOG_HALF_WIDTH = 0.01
# Number of Crank-Nicolson steps replaced by pairs of implicit half-steps
_RANNACHER_STEPS = 2


def price_grid(S0: float, K: float, T: float, sigma: float, M: int) -> np.ndarray:
    """M+1 uniformly spaced price nodes covering spot and strike plus k standard deviations."""
    half_width = max(_GRID_STD_DEVS * sigma * np.sqrt(T), _MIN_LOG_HALF_WIDTH)
    s_min = min(S0, K) * np.exp(-half_width)
    s_max = max(S0, K) * np.exp(half_width)
    return np.linspace(s_min, s_max, M + 1)


def operator_coefficients(S_nodes: np.ndarray, sigma: float, r: float, q: float):
    """Coefficients (a, b, c) of the discretised Black-Scholes operator at interior nodes.

    L(V)_i = a_i V_{i-1} + b_i V_i + c_i V_{i+1}, from central differences of
    1/2 sigma^2 S^2 V_SS + (r - q) S V_S - r V on a uniform grid.
    """
    dS = S_nodes[1] - S_nodes[0]
    S = S_nodes[1:-1]
    diffusion = 0.5 * sigma**2 * S**2 / dS**2
    drift = 0.5 * (r - q) * S / dS
    return diffusion - drift, -(2.0 * diffusion + r), diffusion + drift


def boundary_values(S_lo: float, S_hi: float, K: float, tau: float, r: float, q: float, is_call: bool):
    """Dirichlet values at the grid edges, which are k standard deviations from spot and strike."""
    disc_r, disc_q = np.exp(-r * tau), np.exp(-q * tau)
    if is_call:
        return 0.0, max(S_hi * disc_q - K * disc_r, 0.0)
    return max(K * disc_r - S_lo * disc_q, 0.0), 0.0


class CrankNicolsonPDE:
    """
    Solves the 1D Black-Scholes PDE using second-order Crank-Nicolson finite difference scheme
    with SuperLU pre-factorization.
    """

    def __init__(
        self,
        S0: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = "call",
        M: int = 300,
        N: int = 300,
        q: float = 0.0,
    ) -> None:
        if S0 <= 0 or K <= 0:
            raise ValueError(f"Spot and strike must be positive, got S0={S0}, K={K}")

        self.S0 = float(S0)
        self.K = float(K)
        self.T = max(float(T), 1e-6)  # Guard against T=0
        self.r = float(r)
        self.q = float(q)
        self.sigma = max(float(sigma), 1e-6)
        self.option_type = option_type.lower()

        # Grid parameters (M: Price steps, N: Time steps)
        self.M = int(M)
        self.N = max(int(N), _RANNACHER_STEPS + 1)
        self.S_nodes = price_grid(self.S0, self.K, self.T, self.sigma, self.M)
        self.S_min = float(self.S_nodes[0])
        self.S_max = float(self.S_nodes[-1])
        self.dS = float(self.S_nodes[1] - self.S_nodes[0])
        self.dt = self.T / float(self.N)

    def solve(self) -> float:
        """
        Executes Crank-Nicolson PDE time-stepping and returns the fair option value.
        """
        is_call = self.option_type in ("call", "ce")
        S_nodes = self.S_nodes

        # 1. Terminal Payoff (at maturity tau = 0)
        grid = np.maximum(S_nodes - self.K, 0.0) if is_call else np.maximum(self.K - S_nodes, 0.0)

        a, b, c = operator_coefficients(S_nodes, self.sigma, self.r, self.q)
        size = self.M - 1

        def boundary(tau: float):
            return boundary_values(self.S_min, self.S_max, self.K, tau, self.r, self.q, is_call)

        # 2. Rannacher start-up: implicit Euler half-steps, (I - h L) V_new = V_old + edges
        h = 0.5 * self.dt
        implicit = splu(diags([-h * a[1:], 1.0 - h * b, -h * c[:-1]], [-1, 0, 1], shape=(size, size), format="csc"))
        tau = 0.0
        for _ in range(2 * _RANNACHER_STEPS):
            tau += h
            lo, hi = boundary(tau)
            rhs = grid[1:self.M].copy()
            rhs[0] += h * a[0] * lo
            rhs[-1] += h * c[-1] * hi
            grid[1:self.M] = implicit.solve(rhs)
            grid[0], grid[self.M] = lo, hi

        # 3. Crank-Nicolson for the remaining steps: A V_new = B V_old + edges, with
        #    alpha = dt/2 * a, beta = -dt/2 * b, gamma = dt/2 * c
        alpha, beta, gamma = 0.5 * self.dt * a, -0.5 * self.dt * b, 0.5 * self.dt * c

        # Matrix A (Implicit LHS, time step j+1): -alpha on subdiag, (1+beta) on main, -gamma on superdiag
        A = diags([-alpha[1:], 1.0 + beta, -gamma[:-1]], [-1, 0, 1], shape=(size, size), format="csc")
        # Matrix B (Explicit RHS, time step j): alpha on subdiag, (1-beta) on main, gamma on superdiag
        B = diags([alpha[1:], 1.0 - beta, gamma[:-1]], [-1, 0, 1], shape=(size, size), format="csc")

        # Pre-factorize Matrix A via SuperLU for O(M) linear time backward steps
        A_solver = splu(A)

        for _ in range(self.N - _RANNACHER_STEPS):
            lo_old, hi_old = boundary(tau)
            tau += self.dt
            lo_new, hi_new = boundary(tau)
            rhs = B.dot(grid[1:self.M])
            rhs[0] += alpha[0] * (lo_old + lo_new)
            rhs[-1] += gamma[-1] * (hi_old + hi_new)
            # Solve linear system in O(M) time
            grid[1:self.M] = A_solver.solve(rhs)
            grid[0], grid[self.M] = lo_new, hi_new

        # 4. Interpolate option value at exact S0
        fair_price = float(np.interp(self.S0, S_nodes, grid))
        return float(max(fair_price, 0.0))
