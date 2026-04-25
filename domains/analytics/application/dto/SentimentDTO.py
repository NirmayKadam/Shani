from datetime import datetime
from shared.application.BaseDTO import BaseDTO
from shared.constants import SentimentLabel

class SentimentDTO(BaseDTO):
    symbol: str
    polarity: float
    label: SentimentLabel
    confidence: float
    scored_at: datetime
