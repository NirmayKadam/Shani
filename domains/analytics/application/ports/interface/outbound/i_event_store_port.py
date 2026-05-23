"""
File Overview: Outbound port interface for persisting domain events within the analytics context.

All Functions/Classes:
- i_event_store: Interface for event persistence. Take domain events and send to durable store.
- save_event: Persist domain event. Take base_domain_event and send to TimescaleDB/EventStoreDB.
- get_events: Retrieve recent history. Take symbol/limit and send list of domain events.

Endpoints/APIs: None

Database Tables: None
"""
from abc import ABC, abstractmethod

from typing import List
from shared.domain.base_domain_event import BaseDomainEvent

class IEventStorePort(ABC):
    @abstractmethod
    async def save_event(self, event: BaseDomainEvent) -> None:
        pass
    @abstractmethod
    async def get_events(self, symbol: str, limit: int) -> List[BaseDomainEvent]:
        pass
