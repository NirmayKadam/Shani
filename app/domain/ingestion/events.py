# app/domain/ingestion/events.py — Event schemas for the Ingestion domain
#
# These dataclasses define the shape of events published to the event bus.
# Sentiment domain subscribes to these — never import this file from Sentiment.
# Instead, the Sentiment domain deserialises the JSON payload independently.

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class HeadlineFetchedEvent:
    """Published when a new headline is fetched from NewsAPI."""
    symbol: str
    headline: str
    content: str
    source_url: str
    source_name: str
    published_at: str
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PriceUpdatedEvent:
    """Published when a new price snapshot is fetched via yfinance."""
    symbol: str
    last_price: float
    open: float
    high: float
    low: float
    volume: int
    previous_close: float
    change_percent: float
    market_status: str      # OPEN | CLOSED
    last_updated: str
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OptionsUpdatedEvent:
    """Published when option chain data is fetched from NSE."""
    symbol: str
    spot_price: float
    expiry_dates: list[str]
    total_ce_ticks: int
    total_pe_ticks: int
    ticks: list[dict]       # List of raw tick dicts
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PriceTriggerEvent:
    """Published when a significant price movement is detected."""
    symbol: str
    trigger_type: str       # FLASH_DROP | SPIKE_UP | HIGH_VOLATILITY | VOLUME_ANOMALY
    current_price: float
    previous_price: float
    change_percent: float
    description: str
    triggered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)
