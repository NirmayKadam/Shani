"""
File Overview: Data Transfer Object (DTO) for raw market ticks fetched from exchange feeders.

All Functions/Classes:
- raw_tick_dto: Normalized representation of market price data. Take raw API response and send to analytics ingestion services.

Endpoints/APIs: None

Database Tables: None
"""
from datetime import datetime
from shared.application.dto.base_dto import base_dto

class raw_tick_dto(base_dto):
    symbol: str
    expiry: str
    strike: float
    option_type: str
    oi: int
    volume: int
    ltp: float
    timestamp: datetime
