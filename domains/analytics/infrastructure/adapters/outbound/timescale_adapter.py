from domains.analytics.application.ports.interface.outbound.i_sentiment_store import i_sentiment_store
from domains.analytics.application.ports.interface.outbound.i_event_store import i_event_store
from shared.domain.base_domain_event import base_domain_event
from domains.analytics.domain.entities.sentiment_score import sentiment_score
from typing import List

class timescale_adapter(i_sentiment_store, i_event_store):
    def __init__(self, url: str = None):
        self._url = url
    def save_score(self, score: sentiment_score) -> None: pass
    def get_last_n(self, symbol: str, n: int) -> List[sentiment_score]: return []
    def save_event(self, event: base_domain_event) -> None: pass
    def get_events(self, symbol: str, limit: int) -> List[base_domain_event]: return []
