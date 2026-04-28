"""
File Overview: Versioned domain event schemas and dataclasses for cross-domain communication.

All Functions/Classes:
- VersionedEvent (base class): Shared schema fields.
- HeadlineFetchedV1, PriceUpdatedV1, OptionsUpdatedV1, PriceTriggerV1, SentimentScoredV1, AggregateUpdatedV1, AnalysisRefreshRequestedV1: Specific event payload schemas. Data: Domain Events -> Serialized JSON.

Endpoints/APIs:
- None.

Database Tables:
- None.
"""
from dataclasses import asdict, dataclass, field

from datetime import datetime, timezone
from typing import Any, Literal


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class VersionedEvent:
    """Base schema fields shared by all domain event payloads."""

    event_type: str = field(init=False)
    schema_version: Literal["v1"] = "v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HeadlineFetchedV1(VersionedEvent):
    symbol: str = ""
    headline: str = ""
    content: str = ""
    source_url: str = ""
    source_name: str = ""
    published_at: str = ""
    fetched_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "headline.fetched"


@dataclass(slots=True)
class PriceUpdatedV1(VersionedEvent):
    symbol: str = ""
    last_price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    previous_close: float = 0.0
    change_percent: float = 0.0
    market_status: str = ""
    last_updated: str = ""
    fetched_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "market.price_updated"


@dataclass(slots=True)
class OptionsUpdatedV1(VersionedEvent):
    symbol: str = ""
    spot_price: float = 0.0
    expiry_dates: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "market.options_updated"


@dataclass(slots=True)
class PriceTriggerV1(VersionedEvent):
    symbol: str = ""
    trigger_type: str = ""
    current_price: float = 0.0
    previous_price: float = 0.0
    change_percent: float = 0.0
    description: str = ""
    triggered_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "market.price_trigger"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PriceTriggerV1":
        return cls(
            schema_version="v1",
            symbol=str(payload.get("symbol", "")),
            trigger_type=str(payload.get("trigger_type", "")),
            current_price=float(payload.get("current_price", 0.0)),
            previous_price=float(payload.get("previous_price", 0.0)),
            change_percent=float(payload.get("change_percent", 0.0)),
            description=str(payload.get("description", "")),
            triggered_at=str(payload.get("triggered_at", _utc_now_iso())),
        )


@dataclass(slots=True)
class SentimentScoredV1(VersionedEvent):
    symbol: str = ""
    headline: str = ""
    content: str = ""
    source_url: str = ""
    source_name: str = ""
    published_at: str = ""
    sentiment_label: str = ""
    sentiment_score: float = 0.0
    confidence: float = 0.0
    scored_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "sentiment.scored"


@dataclass(slots=True)
class AggregateUpdatedV1(VersionedEvent):
    symbol: str = ""
    timeframe: str = ""
    label: str = ""
    avg_score: float = 0.0
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0
    neutral_pct: float = 0.0
    count: int = 0
    trend: str = ""
    computed_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "sentiment.aggregate_updated"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AggregateUpdatedV1":
        return cls(
            schema_version="v1",
            symbol=str(payload.get("symbol", "")),
            timeframe=str(payload.get("timeframe", "")),
            label=str(payload.get("label", "NEUTRAL")),
            avg_score=float(payload.get("avg_score", 0.0)),
            bullish_pct=float(payload.get("bullish_pct", 0.0)),
            bearish_pct=float(payload.get("bearish_pct", 0.0)),
            neutral_pct=float(payload.get("neutral_pct", 0.0)),
            count=int(payload.get("count", 0)),
            trend=str(payload.get("trend", "")),
            computed_at=str(payload.get("computed_at", _utc_now_iso())),
        )


@dataclass(slots=True)
class AnalysisRefreshRequestedV1(VersionedEvent):
    symbol: str = ""
    reason: str = "stale_or_partial_read_model"
    requested_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        self.event_type = "analysis.refresh_requested"


# Backward-compatible aliases (existing callers import these names).
HeadlineFetchedEvent = HeadlineFetchedV1
PriceUpdatedEvent = PriceUpdatedV1
OptionsUpdatedEvent = OptionsUpdatedV1
PriceTriggerEvent = PriceTriggerV1
SentimentScoredEvent = SentimentScoredV1
AggregateUpdatedEvent = AggregateUpdatedV1
AnalysisRefreshRequestedEvent = AnalysisRefreshRequestedV1


__all__ = [
    "VersionedEvent",
    "HeadlineFetchedV1",
    "PriceUpdatedV1",
    "OptionsUpdatedV1",
    "PriceTriggerV1",
    "SentimentScoredV1",
    "AggregateUpdatedV1",
    "AnalysisRefreshRequestedV1",
    "HeadlineFetchedEvent",
    "PriceUpdatedEvent",
    "OptionsUpdatedEvent",
    "PriceTriggerEvent",
    "SentimentScoredEvent",
    "AggregateUpdatedEvent",
    "AnalysisRefreshRequestedEvent",
]
