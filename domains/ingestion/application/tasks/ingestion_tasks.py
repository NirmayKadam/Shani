"""
File Overview: Celery tasks for polling news, prices, and options data.

All Functions/Classes:
- get_service: Lazy factory for ingestion service. Take environment config and send service instance.
- poll_news: Celery task. Take symbol list and send to ingestion service news fetcher.
- poll_prices: Celery task. Take symbol list and send to ingestion service price fetcher.
- poll_options: Celery task. Take symbol list and send to ingestion service options fetcher.

Endpoints/APIs: None (Celery Workers)

Database Tables: Redis (Cache, Streams)
"""
import os
import logging

from shared.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)

_service = None


def get_service():
    global _service
    if _service is None:
        from shared.infrastructure.redis_client import get_redis_sync
        from domains.ingestion.infrastructure.adapters.outbound.news_api_adapter import NewsFetcher
        from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import MarketPriceFetcher, OptionChainFetcher
        from domains.ingestion.infrastructure.adapters.outbound.redis_event_bus_adapter import redis_event_bus_adapter
        from domains.ingestion.application.services.ingestion_service import ingestion_service

        redis = get_redis_sync()
        news = NewsFetcher(api_key=os.getenv("NEWS_API_KEY", ""))
        price = MarketPriceFetcher()
        options = OptionChainFetcher()
        bus = redis_event_bus_adapter(redis)
        _service = ingestion_service(news, price, options, redis, bus)
    return _service


@celery_app.task(name="ingestion.poll_news", queue="ingestion")
def poll_news(symbol: str = None):
    import asyncio
    from app.config import get_settings
    from shared.constants import INDEX_SYMBOLS

    svc = get_service()
    if symbol:
        symbols = [symbol]
    else:
        # Use default watchlist from config, fallback to INDEX_SYMBOLS
        symbols = get_settings().get_default_symbols_as_list()
        if not symbols:
            symbols = list(INDEX_SYMBOLS)

    for sym in symbols:
        try:
            from shared.utils.symbol_validator import SymbolValidator
            clean_sym = SymbolValidator.get_clean_symbol(sym)
            asyncio.run(svc.ingest_news(clean_sym))
        except Exception as e:
            logger.error("[%s] poll_news failed: %s", sym, e)


@celery_app.task(name="ingestion.poll_prices", queue="ingestion")
def poll_prices(symbol: str = None):
    import asyncio
    from app.config import get_settings
    from shared.constants import INDEX_SYMBOLS

    svc = get_service()
    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()
        if not symbols:
            symbols = list(INDEX_SYMBOLS)

    for sym in symbols:
        try:
            from shared.utils.symbol_validator import SymbolValidator
            clean_sym = SymbolValidator.get_clean_symbol(sym)
            asyncio.run(svc.ingest_market_data(clean_sym))
        except Exception as e:
            logger.error("[%s] poll_prices failed: %s", sym, e)


@celery_app.task(name="ingestion.poll_options", queue="ingestion")
def poll_options(symbol: str = None):
    import asyncio
    from app.config import get_settings
    from shared.constants import INDEX_SYMBOLS

    svc = get_service()
    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()
        if not symbols:
            symbols = list(INDEX_SYMBOLS)

    for sym in symbols:
        try:
            from shared.utils.symbol_validator import SymbolValidator
            clean_sym = SymbolValidator.get_clean_symbol(sym)
            asyncio.run(svc.ingest_options(clean_sym))
        except Exception as e:
            logger.error("[%s] poll_options failed: %s", sym, e)
