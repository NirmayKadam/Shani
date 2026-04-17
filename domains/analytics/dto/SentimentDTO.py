from datetime import datetime
from shared.dto.BaseDTO import BaseDTO

class SentimentDTO(BaseDTO):
    symbol: str
    polarity: float
    label: str
    confidence: float
    scored_at: datetime
