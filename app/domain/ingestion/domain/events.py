"""Backward-compatible aliases for ingestion event contracts.

Prefer importing from app.shared.event_bus.contracts.
"""

from app.shared.event_bus.contracts import (
    HeadlineFetchedEvent,
    OptionsUpdatedEvent,
    PriceTriggerEvent,
    PriceUpdatedEvent,
)

__all__ = [
    "HeadlineFetchedEvent",
    "PriceUpdatedEvent",
    "OptionsUpdatedEvent",
    "PriceTriggerEvent",
]
