"""
File Overview: Domain entity representing a raw news article in the ingestion context.

All Functions/Classes:
- raw_article: Data structure for un-scored news. Take raw feed data and send to domain events.

Endpoints/APIs: None

Database Tables: None
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RawArticleEntity:
    id: str
    symbol: str
    headline: str
    body: str
    source: str
    published_at: datetime
