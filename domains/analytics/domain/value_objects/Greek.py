"""
File Overview: Value object representing option Greeks.

All Functions/Classes:
- Greek: Immutable data structure for market sensitivities. Take greeks and send value object state.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Greek:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
