from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.dto.RawArticleDTO import RawArticleDTO

class INewsSource(ABC):
    @abstractmethod
    async def fetch_articles(self, symbol: str) -> List[RawArticleDTO]:
        pass
