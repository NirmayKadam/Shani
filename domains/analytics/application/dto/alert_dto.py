from datetime import datetime
from typing import Dict, Any
from shared.application.dto.base_dto import base_dto

class alert_dto(base_dto):
    event_type: str
    symbol: str
    payload: Dict[str, Any]
    fired_at: datetime
