from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

@dataclass
class derivative_snapshot:
    symbol: str
    expiry: str
    pcr: float
    iv_surface: Dict[str, float]
    anomalies: List[str]
    computed_at: datetime
