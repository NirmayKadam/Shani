"""
File Overview: Domain entity representing a temporal snapshot of derivatives metrics.

All Functions/Classes:
- derivative_snapshot: Data structure for options state. Take PCR/IV/Anomalies and send entity state.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass, field

from datetime import datetime
from typing import Dict, List

@dataclass
class DerivativeSnapshotEntity:
    symbol: str
    expiry: str
    pcr: float
    iv_surface: Dict[str, float]
    anomalies: List[str]
    computed_at: datetime
