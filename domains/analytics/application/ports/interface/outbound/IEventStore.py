from abc import ABC, abstractmethod
from typing import List
from shared.domain.BaseDomainEvent import BaseDomainEvent

class IEventStore(ABC):
    @abstractmethod
    def save_event(self, event: BaseDomainEvent) -> None:
        pass
    @abstractmethod
    def get_events(self, symbol: str, limit: int) -> List[BaseDomainEvent]:
        pass
