from dataclasses import dataclass
from datetime import datetime

@dataclass
class RawArticle:
    id: str
    symbol: str
    headline: str
    body: str
    source: str
    published_at: datetime
