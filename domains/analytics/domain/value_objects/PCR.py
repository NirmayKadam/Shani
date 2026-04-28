"""
File Overview: Value object representing the Put-Call Ratio (PCR).

All Functions/Classes:
- PCR: Immutable data structure for derivative volume ratios. Take numeric ratio and send sentiment label.
- interpretation: Logic to map numeric ratio to label. Take value and send BULLISH/BEARISH/NEUTRAL.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PCR:
    value: float
    def interpretation(self) -> str:
        if self.value > 1.2: return "BULLISH"
        if self.value < 0.8: return "BEARISH"
        return "NEUTRAL"
