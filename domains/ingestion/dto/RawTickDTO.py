from datetime import datetime
from shared.dto.BaseDTO import BaseDTO

class RawTickDTO(BaseDTO):
    symbol: str
    expiry: str
    strike: float
    option_type: str
    oi: int
    volume: int
    ltp: float
    timestamp: datetime
