from dataclasses import dataclass
from datetime import datetime

@dataclass
class sentiment_score:
    symbol: str
    polarity: float
    confidence: float
    scored_at: datetime
