from domains.analytics.application.ports.interface.outbound.ISentimentStore import ISentimentStore
from domains.analytics.application.ports.interface.outbound.IEventStore import IEventStore
from shared.domain.BaseDomainEvent import BaseDomainEvent
from domains.analytics.domain.entities.SentimentScore import SentimentScore
from typing import List

class TimescaleAdapter(ISentimentStore, IEventStore):
    def __init__(self, url: str = None):
        self._url = url
    def save_score(self, score: SentimentScore) -> None: pass
    def get_last_n(self, symbol: str, n: int) -> List[SentimentScore]: return []
    def save_event(self, event: BaseDomainEvent) -> None: pass
    def get_events(self, symbol: str, limit: int) -> List[BaseDomainEvent]: return []
