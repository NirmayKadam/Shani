from domains.analytics.ports.inbound.IArticleProcessor import IArticleProcessor
from domains.analytics.ports.inbound.ITickProcessor import ITickProcessor
from typing import List
from domains.ingestion.dto.RawTickDTO import RawTickDTO
from domains.ingestion.dto.RawArticleDTO import RawArticleDTO

class CeleryConsumerAdapter(IArticleProcessor, ITickProcessor):
    def process(self, dto) -> None:
        raise NotImplementedError(" प्रोसेस() not implemented.")
