# app/domain/sentiment/events.py — Event schemas for the Sentiment domain

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class SentimentScoredEvent:
    """Published when a headline is scored by FinBERT."""
    symbol: str
    headline: str
    label: str          # BULLISH | BEARISH | NEUTRAL
    score: float        # -1.0 to +1.0 (polarity)
    confidence: float   # 0.0 to 1.0 (raw FinBERT confidence)
    source_name: str
    published_at: str
    scored_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AggregateUpdatedEvent:
    """Published when sentiment aggregates are recomputed for a timeframe."""
    symbol: str
    timeframe: str      # intraday | daily | weekly | monthly
    label: str          # BULLISH | BEARISH | NEUTRAL
    avg_score: float
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    headline_count: int
    trend: str          # IMPROVING | DETERIORATING | STABLE
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)
