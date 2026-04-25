import os
import logging

from shared.infrastructure.CeleryApp import celery_app

Logger = logging.getLogger(__name__)

_service = None


def get_service():
    global _service
    if _service is None:
        from shared.infrastructure.redis_client import get_redis_sync
        from domains.ingestion.infrastructure.adapters.outbound.NewsApiAdapter import NewsFetcher
        from domains.ingestion.infrastructure.adapters.outbound.NseApiAdapter import MarketPriceFetcher, OptionChainFetcher
        from domains.ingestion.infrastructure.adapters.outbound.RedisEventBusAdapter import RedisEventBusAdapter
        from domains.ingestion.application.services.IngestionService import IngestionService

        redis = get_redis_sync()
        news = NewsFetcher(api_key=os.getenv("NEWS_API_KEY", ""))
        price = MarketPriceFetcher()
        options = OptionChainFetcher()
        bus = RedisEventBusAdapter(redis)
        _service = IngestionService(news, price, options, redis, bus)
    return _service


@celery_app.task(name="ingestion.poll_news", queue="ingestion")
def poll_news(symbol: str = None):
    import asyncio
    from app.config import GetSettings
    from shared.constants import INDEX_SYMBOLS

    svc = get_service()
    if symbol:
        symbols = [symbol]
    else:
        # Use default watchlist from config, fallback to INDEX_SYMBOLS
        symbols = GetSettings().GetDefaultSymbolsAsList()
        if not symbols:
            symbols = list(INDEX_SYMBOLS)

    for sym in symbols:
        try:
            asyncio.run(svc.ingest_news(sym))
        except Exception as e:
            Logger.error("[%s] poll_news failed: %s", sym, e)


@celery_app.task(name="ingestion.poll_prices", queue="ingestion")
def poll_prices(symbol: str = None):
    import asyncio
    from app.config import GetSettings
    from shared.constants import INDEX_SYMBOLS

    svc = get_service()
    if symbol:
        symbols = [symbol]
    else:
        symbols = GetSettings().GetDefaultSymbolsAsList()
        if not symbols:
            symbols = list(INDEX_SYMBOLS)

    for sym in symbols:
        try:
            asyncio.run(svc.ingest_market_data(sym))
        except Exception as e:
            Logger.error("[%s] poll_prices failed: %s", sym, e)


@celery_app.task(name="ingestion.poll_options", queue="ingestion")
def poll_options(symbol: str = None):
    import asyncio
    from app.config import GetSettings
    from shared.constants import INDEX_SYMBOLS

    svc = get_service()
    if symbol:
        symbols = [symbol]
    else:
        symbols = GetSettings().GetDefaultSymbolsAsList()
        if not symbols:
            symbols = list(INDEX_SYMBOLS)

    for sym in symbols:
        try:
            asyncio.run(svc.ingest_options(sym))
        except Exception as e:
            Logger.error("[%s] poll_options failed: %s", sym, e)
