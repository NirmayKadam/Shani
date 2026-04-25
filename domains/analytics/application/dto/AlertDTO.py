from datetime import datetime
from typing import Dict, Any
from shared.application.BaseDTO import BaseDTO

class AlertDTO(BaseDTO):
    event_type: str
    symbol: str
    payload: Dict[str, Any]
    fired_at: datetime
