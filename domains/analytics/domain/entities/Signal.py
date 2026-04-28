"""
File Overview: Domain entity representing a technical trading signal.

All Functions/Classes:
- Signal: Data structure for signal triggers. Take type/SMA value and send entity state.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass

from datetime import datetime

@dataclass
class Signal:
    symbol: str
    signal_type: str
    sma_value: float
    triggered_at: datetime
