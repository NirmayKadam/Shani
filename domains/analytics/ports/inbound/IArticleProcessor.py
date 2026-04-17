from abc import ABC, abstractmethod
from domains.ingestion.dto.RawArticleDTO import RawArticleDTO

class IArticleProcessor(ABC):
    @abstractmethod
    def process(self, dto: RawArticleDTO) -> None:
        pass
