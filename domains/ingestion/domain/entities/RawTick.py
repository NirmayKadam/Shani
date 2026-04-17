from dataclasses import dataclass
from datetime import datetime

@dataclass
class RawTick:
    symbol: str
    expiry: str
    strike: float
    ce_oi: int
    pe_oi: int
    ce_vol: int
    pe_vol: int
    ltp: float
    timestamp: datetime
