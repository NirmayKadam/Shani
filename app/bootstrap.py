"""
File Overview: Composition root for the ingestion service.

Redis clients and aiohttp sessions are bound to the event loop that created them, so the
service is cached per event loop: a Celery worker thread with its own loop gets its own service
instead of one bound to another thread's loop.
"""
import asyncio
import weakref

from shared.infrastructure.redis_client import get_redis_client


class Bootstrap:
    _services: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, object]" = weakref.WeakKeyDictionary()

    @classmethod
    async def get_redis(cls):
        return await get_redis_client()

    @classmethod
    async def get_ingestion_service(cls):
        loop = asyncio.get_running_loop()
        service = cls._services.get(loop)
        if service is None:
            from domains.ingestion.infrastructure.outbound.adapter_factory import get_market_data_adapter
            from domains.ingestion.infrastructure.outbound.redis_event_bus_adapter import RedisEventBusAdapter
            from domains.ingestion.application.services.ingestion_service import IngestionService

            redis = await cls.get_redis()
            market_adapter = get_market_data_adapter(redis_client=redis)
            service = IngestionService(
                price_fetcher=market_adapter,
                option_fetcher=market_adapter,
                event_bus=RedisEventBusAdapter(redis),
                redis_client=redis,
            )
            cls._services[loop] = service
        return service
