from dataclasses import dataclass

@dataclass(frozen=True)
class Greek:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
