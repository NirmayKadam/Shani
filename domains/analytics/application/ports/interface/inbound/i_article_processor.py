from abc import ABC, abstractmethod
from domains.ingestion.application.dto.raw_article_dto import raw_article_dto

class i_article_processor(ABC):
    @abstractmethod
    def process(self, dto: raw_article_dto) -> None:
        pass
