from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.application.dto.RawTickDTO import RawTickDTO

class IMarketDataSource(ABC):
    @abstractmethod
    async def fetch_option_chain(self, symbol: str) -> List[RawTickDTO]:
        pass
