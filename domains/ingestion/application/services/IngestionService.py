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

    async def ingest_news(self, symbol: str):
        import logging
        log = logging.getLogger(__name__)
        
        articles = await self.news.fetch_articles(symbol)
        for article in articles:
            # Simple dedup check (e.g. by URL)
            is_new = await self.dedup.is_new('news', article.url)
            if is_new:
                from domains.ingestion.domain.events.ArticleIngested import ArticleIngested
                event = ArticleIngested(
                    symbol=article.symbol,
                    headline=article.headline,
                    body=article.body,
                    source=article.source,
                    url=article.url,
                    published_at=article.published_at
                )
                await self.pub.publish("ingestion.news", event.to_dict())
                await self.dedup.mark_seen('news', article.url)
        log.info(f"[{symbol}] Ingested {len(articles)} articles")

    async def ingest_market_data(self, symbol: str):
        import logging
        log = logging.getLogger(__name__)

        ticks = await self.mkt.fetch_option_chain(symbol)
        if not ticks:
            return

        from domains.ingestion.domain.events.TickBatchIngested import TickBatchIngested
        event = TickBatchIngested(
            symbol=symbol,
            ticks=[t.to_dict() for t in ticks]
        )
        await self.pub.publish("ingestion.mkt", event.to_dict())
        log.info(f"[{symbol}] Ingested {len(ticks)} ticks")
