import os
from shared.messaging.CeleryApp import CeleryApp as celery_app

# Dependency Injection placeholders
from domains.ingestion.application.services.IngestionService import IngestionService
from domains.ingestion.adapters.outbound.NewsApiAdapter import NewsApiAdapter
from domains.ingestion.adapters.outbound.NseApiAdapter import NseApiAdapter
from domains.ingestion.adapters.outbound.RedisDedupAdapter import RedisDedupAdapter
from domains.ingestion.adapters.outbound.RedisEventBusAdapter import RedisEventBusAdapter

# Configure adapters lazily to avoid connection errors on import
_service = None

def get_service():
    global _service
    if not _service:
        import asyncio
        from shared.messaging.RedisClient import get_redis_sync
        redis = get_redis_sync()
        news_api = NewsApiAdapter(os.getenv("NEWS_API_KEY", ""))
        nse_api = NseApiAdapter()
        dedup = RedisDedupAdapter(redis)
        pub = RedisEventBusAdapter(redis)
        _service = IngestionService(news_api, nse_api, dedup, pub)
    return _service

@celery_app.task(name="ingestion.poll_news", queue="ingestion")
def poll_news(symbol: str):
    import asyncio
    svc = get_service()
    asyncio.run(svc.ingest_news(symbol))

@celery_app.task(name="ingestion.poll_prices", queue="ingestion")
def poll_prices(symbol: str):
    import asyncio
    svc = get_service()
    asyncio.run(svc.ingest_market_data(symbol))
