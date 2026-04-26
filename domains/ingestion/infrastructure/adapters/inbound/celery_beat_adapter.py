from domains.ingestion.application.ports.interface.inbound.i_ingestion_scheduler import i_ingestion_scheduler

class celery_beat_adapter(i_ingestion_scheduler):
    def trigger_news(self, symbol: str) -> None: pass
    def trigger_ticks(self, symbol: str) -> None: pass
