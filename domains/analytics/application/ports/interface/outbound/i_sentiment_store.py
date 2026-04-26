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
