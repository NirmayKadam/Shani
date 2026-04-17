from domains.ingestion.ports.outbound.INewsSource import INewsSource
from domains.ingestion.ports.outbound.IMarketDataSource import IMarketDataSource
from domains.ingestion.ports.outbound.IDedupStore import IDedupStore
from domains.ingestion.ports.outbound.IEventPublisher import IEventPublisher

class IngestionService:
    def __init__(self, news: INewsSource, mkt: IMarketDataSource, dedup: IDedupStore, pub: IEventPublisher):
        self.news = news
        self.mkt = mkt
        self.dedup = dedup
        self.pub = pub

    # TODO: implement orchestrate logic fetch -> dedup -> emit
