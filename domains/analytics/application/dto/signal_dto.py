from datetime import datetime
from shared.application.dto.base_dto import base_dto

class signal_dto(base_dto):
    symbol: str
    signal_type: str
    sma: float
    triggered_at: datetime
