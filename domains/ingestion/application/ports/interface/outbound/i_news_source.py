from abc import ABC, abstractmethod
from typing import List
from domains.ingestion.application.dto.raw_article_dto import raw_article_dto

class i_news_source(ABC):
    @abstractmethod
    async def fetch_articles(self, symbol: str) -> List[raw_article_dto]:
        pass
