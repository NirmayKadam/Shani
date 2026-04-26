from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.application.dto.raw_tick_dto import raw_tick_dto

class i_tick_processor(ABC):
    @abstractmethod
    def process(self, dto: List[raw_tick_dto]) -> None:
        pass
