from dataclasses import dataclass

@dataclass
class ingest_news_command:
    symbol: str
    max_articles: int
