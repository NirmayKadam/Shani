from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.application.dto.RawTickDTO import RawTickDTO

class ITickProcessor(ABC):
    @abstractmethod
    def process(self, dto: List[RawTickDTO]) -> None:
        pass
