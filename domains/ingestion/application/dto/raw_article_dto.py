from datetime import datetime
from shared.application.dto.base_dto import base_dto

class raw_article_dto(base_dto):
    symbol: str
    headline: str
    body: str
    source: str
    published_at: datetime
    url: str
