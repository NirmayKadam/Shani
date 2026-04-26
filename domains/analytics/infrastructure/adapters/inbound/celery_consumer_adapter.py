from domains.analytics.application.ports.interface.inbound.i_article_processor import i_article_processor
from domains.analytics.application.ports.interface.inbound.i_tick_processor import i_tick_processor
from typing import List
from domains.ingestion.application.dto.raw_tick_dto import raw_tick_dto
from domains.ingestion.application.dto.raw_article_dto import raw_article_dto

class celery_consumer_adapter(i_article_processor, i_tick_processor):
    def process(self, dto) -> None:
        raise NotImplementedError(" प्रोसेस() not implemented.")
