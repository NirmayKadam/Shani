from domains.analytics.application.ports.interface.inbound.IArticleProcessor import IArticleProcessor
from domains.analytics.application.ports.interface.inbound.ITickProcessor import ITickProcessor
from typing import List
from domains.ingestion.application.dto.RawTickDTO import RawTickDTO
from domains.ingestion.application.dto.RawArticleDTO import RawArticleDTO

class CeleryConsumerAdapter(IArticleProcessor, ITickProcessor):
    def process(self, dto) -> None:
        raise NotImplementedError(" प्रोसेस() not implemented.")
