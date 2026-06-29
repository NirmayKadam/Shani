"""
File Overview: Domain entities and aggregates for the Analytics context.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from domains.ingestion.application.dto.raw_tick_dto import RawTickDTO
from domains.analytics.domain.events import AnomalyDetectedEvent, SignalFiredEvent

@dataclass
class DerivativeSnapshotEntity:
    symbol: str
    expiry: str
    pcr: float
    iv_surface: Dict[str, float]
    anomalies: List[str]
    computed_at: datetime

@dataclass
class PredictionEntity:
    symbol: str
    bullish_prob: float
    bearish_prob: float
    model_version: str
    predicted_at: datetime

@dataclass
class SentimentScoreEntity:
    symbol: str
    label: str
    score: float
    confidence: float

@dataclass
class SignalEntity:
    symbol: str
    signal_type: str
    sma_value: float
    triggered_at: datetime

class OptionsChainAggregate:
    OI_SURGE_THRESHOLD = 3.0
    VOL_SWEEP_THRESHOLD = 5.0

    def __init__(self):
        self.ticks: List[RawTickDTO] = []
        
    def add_tick_batch(self, ticks: List[RawTickDTO]) -> List[AnomalyDetectedEvent]:
        self.ticks.extend(ticks)
        return self.detect_anomalies()
        
    def detect_anomalies(self) -> List[AnomalyDetectedEvent]:
        anomalies = []
        for tick in self.ticks:
            pass # TODO: EWM logic
        return anomalies

class SentimentAggregate:
    def __init__(self, limit: int = 20):
        self.scores: List[SentimentScoreEntity] = []
        self.limit = limit
        
    def add_score(self, score: SentimentScoreEntity) -> Optional[SignalFiredEvent]:
        self.scores.append(score)
        if len(self.scores) > self.limit:
            self.scores.pop(0)
        return self.compute_sma_and_check()
        
    def compute_sma_and_check(self) -> Optional[SignalFiredEvent]:
        if not self.scores:
            return None
        sma = sum(s.score for s in self.scores) / len(self.scores)
        if sma > 0.5:
            return SignalFiredEvent(payload={"symbol": self.scores[-1].symbol, "signal_type": "BULL_SMA", "sma": sma, "crossover_direction": "UP"})
        return None
