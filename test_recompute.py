import asyncio
import os
import logging
from domains.analytics.application.services.nlp.sentiment_orchestrator import recompute_and_publish_aggregates, SubscriberDependencies
from domains.analytics.application.services.nlp.analyzer import SentimentAnalyzer
from domains.analytics.application.services.nlp.finbert_engine import FinBertEngine
from domains.analytics.application.services.nlp.timeframes import TimeframeComputer
from shared.infrastructure.database import GetDatabasePool
from shared.infrastructure.redis_client import get_redis_client
from shared.infrastructure.event_bus.streams import DurableEventStream
from app.config import get_settings

logging.basicConfig(level=logging.INFO)

async def test():
    cfg = get_settings()
    redis = await get_redis_client()
    db_pool = await GetDatabasePool()
    finbert_engine = FinBertEngine.get_instance(cache_path=cfg.ModelCacheDir)
    analyzer = SentimentAnalyzer(finbert_engine)
    
    deps = SubscriberDependencies(
        analyzer=analyzer,
        timeframe_computer=TimeframeComputer(),
        inference_engine=None,
        redis=redis,
        db_pool=db_pool,
        stream_bus=DurableEventStream(redis),
    )
    
    print("Testing recompute for NIFTY...")
    res = await recompute_and_publish_aggregates("NIFTY", deps)
    print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(test())
