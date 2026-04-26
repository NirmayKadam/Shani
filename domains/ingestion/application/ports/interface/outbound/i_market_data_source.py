from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.application.dto.raw_tick_dto import raw_tick_dto

class i_market_data_source(ABC):
    @abstractmethod
    async def fetch_option_chain(self, symbol: str) -> List[raw_tick_dto]:
        pass
