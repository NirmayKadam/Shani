"""
File Overview: Value object representing a financial instrument ticker symbol.

All Functions/Classes:
- Symbol: Validated instrument identifier. Take string symbol and send validated uppercase state.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Symbol:
    value: str
    def __post_init__(self):
        if not self.value.isupper():
            raise ValueError("Symbol must be uppercase")
