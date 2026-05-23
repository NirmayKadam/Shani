"""
File Overview: Domain entity representing a calculated sentiment score.

All Functions/Classes:
- sentiment_score (class): Data structure for NLP outputs. Data: polarity/confidence -> Entity state.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from dataclasses import dataclass

from datetime import datetime

@dataclass
class SentimentScoreEntity:
    symbol: str
    label: str
    score: float
    confidence: float
