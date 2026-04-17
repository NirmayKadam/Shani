from datetime import datetime
from typing import Dict, List
from shared.dto.BaseDTO import BaseDTO

class DerivativesDTO(BaseDTO):
    symbol: str
    pcr: float
    iv_surface: Dict[str, float]
    anomalies: List[str]
    computed_at: datetime
