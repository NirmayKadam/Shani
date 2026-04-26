from dataclasses import dataclass

@dataclass
class ingest_ticks_command:
    symbol: str
    expiry: str
