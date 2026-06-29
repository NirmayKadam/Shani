from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.application.dto.raw_article_dto import RawArticleDTO

class INewsSourcePort(ABC):
    @abstractmethod
    async def fetch_articles(self, symbol: str) -> List[RawArticleDTO]:
        pass
