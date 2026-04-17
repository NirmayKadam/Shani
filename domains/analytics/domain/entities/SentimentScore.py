from dataclasses import dataclass
from datetime import datetime

@dataclass
class SentimentScore:
    symbol: str
    polarity: float
    confidence: float
    scored_at: datetime
