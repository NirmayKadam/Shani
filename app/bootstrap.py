import os
from functools import lru_cache
from app.config.settings import get_settings
from shared.infrastructure.redis_client import get_redis_client

class Bootstrap:
    _redis_client = None
    _ingestion_service = None
    _sentiment_orchestrator_deps = None

    @classmethod
    async def get_redis(cls):
        if cls._redis_client is None:
            cls._redis_client = await get_redis_client()
        return cls._redis_client

    @classmethod
    async def get_ingestion_service(cls):
        if cls._ingestion_service is None:
            from domains.ingestion.infrastructure.outbound.news_api_adapter import NewsApiAdapter
            from domains.ingestion.infrastructure.outbound.adapter_factory import get_market_data_adapter
            from domains.ingestion.infrastructure.outbound.redis_event_bus_adapter import RedisEventBusAdapter
            from domains.ingestion.infrastructure.outbound.redis_dedup_adapter import RedisDedupAdapter
            from domains.ingestion.application.services.ingestion_service import IngestionService
            
            settings = get_settings()
            redis = await cls.get_redis()
            
            news = NewsApiAdapter(api_key=settings.NewsApiKey)
            market_adapter = get_market_data_adapter(redis_client=redis)
            bus = RedisEventBusAdapter(redis)
            dedup = RedisDedupAdapter(settings.RedisUrl)
            
            cls._ingestion_service = IngestionService(
                news_fetcher=news,
                price_fetcher=market_adapter,
                option_fetcher=market_adapter,
                dedup_store=dedup,
                event_bus=bus,
                redis_client=redis
            )
        return cls._ingestion_service

    @classmethod
    async def get_sentiment_subscriber_deps(cls):
        if cls._sentiment_orchestrator_deps is None:
            from domains.analytics.application.services.nlp.sentiment_orchestrator_service import SubscriberDependencies
            from domains.analytics.application.services.nlp.fin_bert_scorer_service import FinBertScorerService
            from domains.analytics.application.services.nlp.timeframes_service import TimeframeComputerService
            from domains.analytics.application.services.ml_forecasting.daily_predictor_service import DailyPredictorService
            from domains.analytics.application.services.nlp.signal_composer_service import SignalComposerService
            from domains.analytics.infrastructure.outbound.timescale_adapter import TimescaleAdapter
            from domains.analytics.infrastructure.outbound.redis_adapter import RedisAdapter
            
            redis_adapter = RedisAdapter()
            cls._sentiment_orchestrator_deps = SubscriberDependencies(
                scorer=FinBertScorerService(),
                timeframe_computer=TimeframeComputerService(),
                predictor=DailyPredictorService(),
                composer=SignalComposerService(),
                cache=redis_adapter,
                store=TimescaleAdapter(),
                publisher=redis_adapter
            )
        return cls._sentiment_orchestrator_deps
