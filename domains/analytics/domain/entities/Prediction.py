from dataclasses import dataclass
from datetime import datetime

@dataclass
class Prediction:
    symbol: str
    bullish_prob: float
    bearish_prob: float
    model_version: str
    predicted_at: datetime
