from datetime import datetime
from shared.dto.BaseDTO import BaseDTO

class RawArticleDTO(BaseDTO):
    symbol: str
    headline: str
    body: str
    source: str
    published_at: datetime
    url: str
