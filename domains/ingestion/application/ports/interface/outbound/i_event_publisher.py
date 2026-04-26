from abc import ABC, abstractmethod
from shared.domain.base_domain_event import base_domain_event

class i_event_publisher(ABC):
    @abstractmethod
    def publish(self, event: base_domain_event) -> None:
        pass
