"""Backward-compatible aliases for sentiment event contracts.

Prefer importing from shared.infrastructure.event_bus.contracts.
"""

from shared.infrastructure.event_bus.contracts import AggregateUpdatedEvent, SentimentScoredEvent

__all__ = ["SentimentScoredEvent", "AggregateUpdatedEvent"]
