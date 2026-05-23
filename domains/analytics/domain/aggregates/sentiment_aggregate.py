"""
File Overview: Aggregate for managing sentiment scores and triggering crossover signals.

All Functions/Classes:
- sentiment_aggregate (class): Main aggregate for sentiment trending. Data: scores -> signal events.
- add_score: Buffers scores and evaluates SMA. Data: sentiment_score -> signal_fired event.
- compute_sma_and_check: Calculates rolling average. Data: buffer -> signal trigger.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from typing import List, Optional

from domains.analytics.domain.entities.sentiment_score_entity import SentimentScoreEntity
from domains.analytics.domain.events.signal_fired_event import SignalFiredEvent

class SentimentAggregate:
    def __init__(self, limit: int = 20):
        self.scores: List[sentiment_score] = []
        self.limit = limit
        
    def add_score(self, score: SentimentScoreEntity) -> Optional[SignalFiredEvent]:
        self.scores.append(score)
        if len(self.scores) > self.limit:
            self.scores.pop(0)
        return self.compute_sma_and_check()
        
    def compute_sma_and_check(self) -> Optional[SignalFiredEvent]:
        if not self.scores:
            return None
        sma = sum(s.polarity for s in self.scores) / len(self.scores)
        if sma > 0.5:
            return SignalFiredEvent(payload={"symbol": self.scores[-1].symbol, "signal_type": "BULL_SMA", "sma": sma, "crossover_direction": "UP"})
        return None
