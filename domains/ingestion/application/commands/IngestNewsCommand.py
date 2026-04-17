from dataclasses import dataclass

@dataclass
class IngestNewsCommand:
    symbol: str
    max_articles: int
