"""
File Overview: Celery tasks for polling news, prices, and options data.
Each task resolves symbols via SymbolValidator and delegates to ingestion_service.
Uses a persistent event loop per worker thread to avoid recreating connections.

All Functions/Classes:
- _get_or_create_loop: Thread-local event loop factory. Data: threading.local -> asyncio loop.
- _get_or_create_service: Cached service per event loop. Data: loop -> IngestionService.
- poll_news: Celery task. Data: symbol list -> ingestion service news fetcher.
- poll_prices: Celery task. Data: symbol list -> ingestion service price fetcher.
- poll_options: Celery task. Data: symbol list -> ingestion service options fetcher.

Endpoints/APIs: None (Celery Workers)

Database Tables: Redis (Cache, Streams)
"""
import os
import logging
import asyncio
import threading

from shared.infrastructure.celery_app import celery_app
from shared.utils.symbol_validator import SymbolValidator

logger = logging.getLogger(__name__)

# ── Persistent loop per worker thread ────────────────────────────
_thread_local = threading.local()
_service_cache_lock = asyncio.Lock() if False else None  # placeholder, real lock created per-loop


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent event loop for this worker thread.

    Celery prefork workers each get their own thread; we keep one loop
    alive for the lifetime of the thread instead of calling asyncio.run()
    (which creates + destroys a loop every task invocation).
    """
    if not hasattr(_thread_local, 'loop') or _thread_local.loop.is_closed():
        _thread_local.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_thread_local.loop)
        _thread_local.service = None  # Reset service when loop changes
    return _thread_local.loop


async def _get_or_create_service():
    """Return a cached IngestionService bound to the current event loop.

    Connections (Redis, aiohttp) are bound to the loop that created them,
    so we cache per-loop and reuse across task invocations.
    """
    if getattr(_thread_local, 'service', None) is not None:
        return _thread_local.service

    from shared.infrastructure.redis_client import get_redis_client
    from domains.ingestion.infrastructure.adapters.outbound.news_api_adapter import NewsApiAdapter
    from domains.ingestion.infrastructure.adapters.outbound.adapter_factory import get_market_data_adapter
    from domains.ingestion.infrastructure.adapters.outbound.redis_event_bus_adapter import RedisEventBusAdapter
    from domains.ingestion.infrastructure.adapters.outbound.redis_dedup_adapter import RedisDedupAdapter
    from domains.ingestion.application.services.ingestion_service import IngestionService

    redis = await get_redis_client()
    news = NewsApiAdapter(api_key=os.getenv("NEWS_API_KEY", ""))
    market_adapter = get_market_data_adapter(redis_client=redis)
    bus = RedisEventBusAdapter(redis)
    dedup = RedisDedupAdapter(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    svc = IngestionService(news, market_adapter, market_adapter, dedup, bus, redis)

    _thread_local.service = svc
    return svc


@celery_app.task(name="ingestion.poll_news", queue="ingestion")
def poll_news(symbol: str = None):
    from app.config import get_settings

    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()

    loop = _get_or_create_loop()

    async def _run_batch():
        svc = await _get_or_create_service()
        tasks = []
        for sym in symbols:
            clean_sym = SymbolValidator.get_clean_symbol(sym)
            tasks.append(svc.ingest_news(clean_sym))
        await asyncio.gather(*tasks, return_exceptions=True)

    loop.run_until_complete(_run_batch())


@celery_app.task(name="ingestion.poll_prices", queue="ingestion")
def poll_prices(symbol: str = None):
    from app.config import get_settings

    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()

    loop = _get_or_create_loop()

    async def _run_batch():
        svc = await _get_or_create_service()
        tasks = []
        for sym in symbols:
            clean_sym = SymbolValidator.get_clean_symbol(sym)
            tasks.append(svc.ingest_market_data(clean_sym))
        await asyncio.gather(*tasks, return_exceptions=True)

    loop.run_until_complete(_run_batch())


@celery_app.task(name="ingestion.poll_options", queue="ingestion")
def poll_options(symbol: str = None):
    from app.config import get_settings

    if symbol:
        symbols = [symbol]
    else:
        symbols = get_settings().get_default_symbols_as_list()

    loop = _get_or_create_loop()

    async def _run_batch():
        svc = await _get_or_create_service()
        tasks = []
        for sym in symbols:
            clean_sym = SymbolValidator.get_clean_symbol(sym)
            tasks.append(svc.ingest_options(clean_sym))
        await asyncio.gather(*tasks, return_exceptions=True)

    loop.run_until_complete(_run_batch())
