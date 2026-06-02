"""
File Overview: Implementation of the Crank-Nicolson Partial Differential Equation (PDE) solver for option pricing.

Key Functions/Classes:
- CrankNicolsonPDE: Main class for solving the PDE grid.
- solve: Executes the backward time loop to compute the option price.

Endpoints/APIs: None

Database Tables: None
"""
import numpy as np

from scipy.sparse import diags
from scipy.sparse.linalg import spsolve

class CrankNicolsonPDE:
    def __init__(self, S0: float, K: float, T: float, r: float, sigma: float, option_type: str = 'call', M: int = 200, N: int = 200):
        self.S0 = S0
        self.K = K
        self.T = max(T, 1e-6)  # Guard against T=0
        self.r = r
        self.sigma = max(sigma, 1e-6)
        self.option_type = option_type.lower()
        
        # Grid parameters (M: Price steps, N: Time steps)
        self.M = M
        self.N = N
        # S_max should be large enough to minimize boundary error. 
        # Standard: 3-4x Strike or Strike + 3*sigma*sqrt(T)
        self.S_max = max(3 * K, S0 * 2.5) 
        self.dS = self.S_max / self.M
        self.dt = self.T / self.N

        # CFL stability check: clamp dt if explicit part of Crank-Nicolson
        # could become unstable for large sigma or fine grids.
        # The stability limit is dt <= 1 / (sigma^2 * M^2) for the explicit term.
        if sigma > 0:
            dt_max = 0.9 / (sigma**2 * M**2) * (self.S_max**2 / 1.0)  # Scaled for grid
            if self.dt > dt_max and dt_max > 0:
                self.N = max(int(self.T / dt_max) + 1, N)
                self.dt = self.T / self.N
        
    def solve(self) -> float:
        # 1. Setup the grid
        S_nodes = np.linspace(0, self.S_max, self.M + 1)
        grid = np.zeros(self.M + 1)
        
        # 2. Terminal Conditions (At Expiration)
        if self.option_type == 'call':
            grid = np.maximum(S_nodes - self.K, 0)
        else:
            grid = np.maximum(self.K - S_nodes, 0)
            
        # 3. Tridiagonal Matrix Coefficients
        #    Sign convention: alpha/beta/gamma are defined for the *explicit* side.
        #    Matrix A (implicit, LHS) uses negated off-diagonals and (1 - beta) on main.
        #    Matrix B (explicit, RHS) uses original signs and (1 + beta) on main.
        i = np.arange(1, self.M)
        alpha = -0.25 * self.dt * ((self.sigma**2 * i**2) - (self.r * i))
        beta = 0.5 * self.dt * ((self.sigma**2 * i**2) + self.r)
        gamma = -0.25 * self.dt * ((self.sigma**2 * i**2) + (self.r * i))
        
        # Matrix A (Implicit side) and Matrix B (Explicit side)
        A = diags([-alpha[1:], 1 - beta, -gamma[:-1]], [-1, 0, 1], format='csc')
        B = diags([alpha[1:], 1 + beta, gamma[:-1]], [-1, 0, 1], format='csc')
        
        # 4. Backward Time Loop (Solve A * V_new = B * V_old)
        for j in range(self.N - 1, -1, -1):
            # Compute RHS
            rhs = B.dot(grid[1:self.M])
            
            # Boundary Conditions (Implicit + Explicit contributions)
            t_new = j * self.dt
            t_old = (j + 1) * self.dt
            
            if self.option_type == 'call':
                # S=0 boundary is 0 for Call
                # S_max boundary is S_max - K * e^(-r * (T - t))
                v_new_bound = self.S_max - self.K * np.exp(-self.r * (self.T - t_new))
                v_old_bound = self.S_max - self.K * np.exp(-self.r * (self.T - t_old))
                rhs[-1] += gamma[-1] * (v_new_bound + v_old_bound)
            else:
                # S=0 boundary is K * e^(-r * (T - t)) for Put
                # S_max boundary is 0 for Put
                v_new_bound = self.K * np.exp(-self.r * (self.T - t_new))
                v_old_bound = self.K * np.exp(-self.r * (self.T - t_old))
                rhs[0] += alpha[0] * (v_new_bound + v_old_bound)

            # Solve the system
            grid[1:self.M] = spsolve(A, rhs)
            
        # 5. Interpolate final price to match exact S0
        return float(np.interp(self.S0, S_nodes, grid))
