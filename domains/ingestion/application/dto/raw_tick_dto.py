from datetime import datetime
from shared.application.dto.base_dto import base_dto

class raw_tick_dto(base_dto):
    symbol: str
    expiry: str
    strike: float
    option_type: str
    oi: int
    volume: int
    ltp: float
    timestamp: datetime
