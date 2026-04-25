from abc import ABC, abstractmethod
from typing import List
from domains.analytics.domain.entities.SentimentScore import SentimentScore

class ISentimentStore(ABC):
    @abstractmethod
    def save_score(self, score: SentimentScore) -> None:
        pass
    @abstractmethod
    def get_last_n(self, symbol: str, n: int) -> List[SentimentScore]:
        pass
