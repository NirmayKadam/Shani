from typing import List, Optional
from domains.analytics.domain.entities.sentiment_score import sentiment_score
from domains.analytics.domain.events.signal_fired import signal_fired

class sentiment_aggregate:
    def __init__(self, limit: int = 20):
        self.scores: List[sentiment_score] = []
        self.limit = limit
        
    def add_score(self, score: sentiment_score) -> Optional[signal_fired]:
        self.scores.append(score)
        if len(self.scores) > self.limit:
            self.scores.pop(0)
        return self.compute_sma_and_check()
        
    def compute_sma_and_check(self) -> Optional[signal_fired]:
        if not self.scores:
            return None
        sma = sum(s.polarity for s in self.scores) / len(self.scores)
        if sma > 0.5:
            return signal_fired(payload={"symbol": self.scores[-1].symbol, "signal_type": "BULL_SMA", "sma": sma, "crossover_direction": "UP"})
        return None
