"""Backward-compatible aliases for sentiment event contracts.

Prefer importing from app.shared.event_bus.contracts.
"""

from app.shared.event_bus.contracts import AggregateUpdatedEvent, SentimentScoredEvent

__all__ = ["SentimentScoredEvent", "AggregateUpdatedEvent"]
