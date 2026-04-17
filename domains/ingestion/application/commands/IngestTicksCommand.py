from dataclasses import dataclass

@dataclass
class IngestTicksCommand:
    symbol: str
    expiry: str
