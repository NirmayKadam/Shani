"""
File Overview: Domain entity representing a raw market tick (price/volume snapshot).

All Functions/Classes:
- raw_tick: Data structure for raw market snapshots. Take API data and send to event bus.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass
class raw_tick:
    symbol: str
    expiry: str
    strike: float
    ce_oi: int
    pe_oi: int
    ce_vol: int
    pe_vol: int
    ltp: float
    timestamp: datetime
