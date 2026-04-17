from datetime import datetime
from shared.dto.BaseDTO import BaseDTO

class SignalDTO(BaseDTO):
    symbol: str
    signal_type: str
    sma: float
    triggered_at: datetime
