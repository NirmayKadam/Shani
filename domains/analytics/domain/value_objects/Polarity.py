"""
File Overview: Value object representing NLP sentiment polarity.

All Functions/Classes:
- Polarity: Immutable data structure for sentiment scores. Take numeric polarity and send domain label.
- label: Logic to map numeric polarity to label. Take value and send BULLISH/BEARISH/NEUTRAL.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Polarity:
    value: float
    def label(self) -> str:
        if self.value > 0.1: return "BULLISH"
        if self.value < -0.1: return "BEARISH"
        return "NEUTRAL"
