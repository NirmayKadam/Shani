from datetime import datetime
from shared.application.dto.base_dto import base_dto
from shared.constants import SentimentLabel

class sentiment_dto(base_dto):
    symbol: str
    polarity: float
    label: SentimentLabel
    confidence: float
    scored_at: datetime
