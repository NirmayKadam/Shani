from typing import List, Optional
from domains.analytics.domain.entities.SentimentScore import SentimentScore
from domains.analytics.domain.events.SignalFired import SignalFired

class SentimentAggregate:
    def __init__(self, limit: int = 20):
        self.scores: List[SentimentScore] = []
        self.limit = limit
        
    def add_score(self, score: SentimentScore) -> Optional[SignalFired]:
        self.scores.append(score)
        if len(self.scores) > self.limit:
            self.scores.pop(0)
        return self.compute_sma_and_check()
        
    def compute_sma_and_check(self) -> Optional[SignalFired]:
        if not self.scores:
            return None
        sma = sum(s.polarity for s in self.scores) / len(self.scores)
        if sma > 0.5:
            return SignalFired(payload={"symbol": self.scores[-1].symbol, "signal_type": "BULL_SMA", "sma": sma, "crossover_direction": "UP"})
        return None
