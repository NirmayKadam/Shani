from abc import ABC, abstractmethod
from typing import List
from shared.domain.base_domain_event import base_domain_event

class i_event_store(ABC):
    @abstractmethod
    def save_event(self, event: base_domain_event) -> None:
        pass
    @abstractmethod
    def get_events(self, symbol: str, limit: int) -> List[base_domain_event]:
        pass
