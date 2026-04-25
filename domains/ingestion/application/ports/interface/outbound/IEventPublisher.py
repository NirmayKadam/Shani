from abc import ABC, abstractmethod
from shared.domain.BaseDomainEvent import BaseDomainEvent

class IEventPublisher(ABC):
    @abstractmethod
    def publish(self, event: BaseDomainEvent) -> None:
        pass
