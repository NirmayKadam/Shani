from datetime import datetime
from shared.application.BaseDTO import BaseDTO

class SignalDTO(BaseDTO):
    symbol: str
    signal_type: str
    sma: float
    triggered_at: datetime
