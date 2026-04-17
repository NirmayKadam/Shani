from abc import ABC, abstractmethod
from shared.events.BaseDomainEvent import BaseDomainEvent

class IEventPublisher(ABC):
    @abstractmethod
    def publish(self, event: BaseDomainEvent) -> None:
        pass
