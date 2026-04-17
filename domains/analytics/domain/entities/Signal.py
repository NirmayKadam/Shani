from dataclasses import dataclass
from datetime import datetime

@dataclass
class Signal:
    symbol: str
    signal_type: str
    sma_value: float
    triggered_at: datetime
