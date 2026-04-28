"""
File Overview: Inbound adapter for Celery Beat to trigger scheduled ingestion tasks.

All Functions/Classes:
- celery_beat_adapter: Implementation of ingestion scheduler. Take schedule signals and send to Celery tasks.
- trigger_news: Trigger news poll. Take symbol and send to poll_news task.
- trigger_ticks: Trigger price poll. Take symbol and send to poll_prices task.

Endpoints/APIs: None

Database Tables: None
"""
from domains.ingestion.application.ports.interface.inbound.i_ingestion_scheduler import i_ingestion_scheduler

class celery_beat_adapter(i_ingestion_scheduler):
    def trigger_news(self, symbol: str) -> None: pass
    def trigger_ticks(self, symbol: str) -> None: pass
