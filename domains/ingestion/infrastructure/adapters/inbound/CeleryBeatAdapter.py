from domains.ingestion.application.ports.interface.inbound.IIngestionScheduler import IIngestionScheduler

class CeleryBeatAdapter(IIngestionScheduler):
    def trigger_news(self, symbol: str) -> None: pass
    def trigger_ticks(self, symbol: str) -> None: pass
