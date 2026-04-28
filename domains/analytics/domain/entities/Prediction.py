"""
File Overview: Domain entity representing a calculated ML prediction.

All Functions/Classes:
- Prediction: Data structure for inference outputs. Take probabilities/metadata and send entity state.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass

from datetime import datetime

@dataclass
class Prediction:
    symbol: str
    bullish_prob: float
    bearish_prob: float
    model_version: str
    predicted_at: datetime
