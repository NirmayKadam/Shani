"""
File Overview: Celery tasks for polling news, prices, and options data.
Each task resolves symbols via SymbolValidator and delegates to ingestion_service.

All Functions/Classes:
- get_service: Lazy factory for ingestion service. Data: env config -> service instance.
- poll_news: Celery task. Data: symbol list -> ingestion service news fetcher.
- poll_prices: Celery task. Data: symbol list -> ingestion service price fetcher.
- poll_options: Celery task. Data: symbol list -> ingestion service options fetcher.

Endpoints/APIs: None (Celery Workers)

Database Tables: Redis (Cache, Streams)
"""
import os
import logging
import asyncio

from shared.infrastructure.celery_app import celery_app
from shared.utils.symbol_validator import SymbolValidator

logger = logging.getLogger(__name__)

async def _create_service():
    """Create a fresh service instance per asyncio.run() invocation.

    Each Celery task uses asyncio.run() which creates a new event loop.
    Async clients (Redis, aiohttp) are bound to the loop that created them,
    so we must NOT cache them across asyncio.run() boundaries.
    """
    from shared.infrastructure.redis_client import get_redis_client
    from domains.ingestion.infrastructure.adapters.outbound.news_api_adapter import NewsApiAdapter
    from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import NseApiAdapter
    from domains.ingestion.infrastructure.adapters.outbound.redis_event_bus_adapter import RedisEventBusAdapter
    from domains.ingestion.infrastructure.adapters.outbound.redis_dedup_adapter import RedisDedupAdapter
    from domains.ingestion.application.services.ingestion_service import IngestionService

    # Reset the module-level async Redis singleton so it binds to the current loop
    import shared.infrastructure.redis_client as _rc
    _rc._redis_client = None

    redis = await get_redis_client()
    news = NewsApiAdapter(api_key=os.getenv("NEWS_API_KEY", ""))
    nse_adapter = NseApiAdapter()
    bus = RedisEventBusAdapter(redis)
    dedup = RedisDedupAdapter(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return IngestionService(news, nse_adapter, nse_adapter, dedup, bus, redis)


@celery_app.task(name="ingestion.poll_news", queue="ingestion")
def poll_news(symbol: str = None):
    from app.config import get_settings

    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()

    async def _run_batch():
        from shared.infrastructure.redis_client import close_redis_client
        from shared.infrastructure.database import close_database_pool
        try:
            svc = await _create_service()
            tasks = []
            for sym in symbols:
                clean_sym = SymbolValidator.get_clean_symbol(sym)
                tasks.append(svc.ingest_news(clean_sym))

            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await close_redis_client()
            await close_database_pool()

    asyncio.run(_run_batch())


@celery_app.task(name="ingestion.poll_prices", queue="ingestion")
def poll_prices(symbol: str = None):
    from app.config import get_settings

    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()

    async def _run_batch():
        from shared.infrastructure.redis_client import close_redis_client
        from shared.infrastructure.database import close_database_pool
        try:
            svc = await _create_service()
            tasks = []
            for sym in symbols:
                clean_sym = SymbolValidator.get_clean_symbol(sym)
                tasks.append(svc.ingest_market_data(clean_sym))

            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await close_redis_client()
            await close_database_pool()

    asyncio.run(_run_batch())


@celery_app.task(name="ingestion.poll_options", queue="ingestion")
def poll_options(symbol: str = None):
    from app.config import get_settings

    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()

    async def _run_batch():
        from shared.infrastructure.redis_client import close_redis_client
        from shared.infrastructure.database import close_database_pool
        try:
            svc = await _create_service()
            tasks = []
            for sym in symbols:
                clean_sym = SymbolValidator.get_clean_symbol(sym)
                tasks.append(svc.ingest_options(clean_sym))

            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await close_redis_client()
            await close_database_pool()

    asyncio.run(_run_batch())
