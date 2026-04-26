from datetime import datetime
from shared.application.dto.base_dto import base_dto

class prediction_dto(base_dto):
    symbol: str
    bullish_prob: float
    model_version: str
    predicted_at: datetime
