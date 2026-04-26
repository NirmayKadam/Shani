from datetime import datetime
from typing import Dict, List
from shared.application.dto.base_dto import base_dto

class derivatives_dto(base_dto):
    symbol: str
    pcr: float
    iv_surface: Dict[str, float]
    anomalies: List[str]
    computed_at: datetime
