from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class HeadlineFetchedEvent:
    symbol: str
    headline: str
    content: str
    source_url: str
    source_name: str
    published_at: str
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PriceUpdatedEvent:
    symbol: str
    last_price: float
    open: float
    high: float
    low: float
    volume: int
    previous_close: float
    change_percent: float
    market_status: str
    last_updated: str
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OptionsUpdatedEvent:
    symbol: str
    spot_price: float
    expiry_dates: list[str]
    summary: dict[str, Any]
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PriceTriggerEvent:
    symbol: str
    trigger_type: str
    current_price: float
    previous_price: float
    change_percent: float
    description: str
    triggered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PriceTriggerEvent":
        return cls(
            symbol=str(payload.get("symbol", "")),
            trigger_type=str(payload.get("trigger_type", "")),
            current_price=float(payload.get("current_price", 0.0)),
            previous_price=float(payload.get("previous_price", 0.0)),
            change_percent=float(payload.get("change_percent", 0.0)),
            description=str(payload.get("description", "")),
            triggered_at=str(payload.get("triggered_at", datetime.now(timezone.utc).isoformat())),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SentimentScoredEvent:
    symbol: str
    headline: str
    content: str
    source_url: str
    source_name: str
    published_at: str
    sentiment_label: str
    sentiment_score: float
    confidence: float
    scored_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AggregateUpdatedEvent:
    symbol: str
    timeframe: str
    label: str
    avg_score: float
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    count: int
    trend: str
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
