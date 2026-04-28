"""
File Overview: Outbound port interface for persisting sentiment scores. Contract for domain's long-term history.

All Functions/Classes:
- i_sentiment_store: Interface for sentiment persistence. Take score entities and send to database.
- save_score: Write score to persistent store. Take sentiment_score and send to Postgres.
- get_last_n: Query latest scores. Take symbol/count and send list of entities.

Endpoints/APIs: None

Database Tables: None
"""
from abc import ABC, abstractmethod

from typing import List
from domains.analytics.domain.entities.sentiment_score import sentiment_score

class i_sentiment_store(ABC):
    @abstractmethod
    def save_score(self, score: sentiment_score) -> None:
        pass
    @abstractmethod
    def get_last_n(self, symbol: str, n: int) -> List[sentiment_score]:
        pass
