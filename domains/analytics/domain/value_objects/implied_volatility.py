"""
File Overview: Value object representing implied volatility (IV).

All Functions/Classes:
- implied_volatility: Immutable data structure for IV metrics. Take numeric IV and send elevation state.
- is_elevated: Check if IV exceeds threshold. Take threshold and send boolean.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class implied_volatility:
    value: float
    def is_elevated(self, threshold: float) -> bool:
        return self.value > threshold
