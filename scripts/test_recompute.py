import asyncio
import os
import logging
from domains.analytics.application.services.nlp.sentiment_orchestrator_service import (
    recompute_and_publish_aggregates, 
    SubscriberDependencies
)
from domains.analytics.application.services.nlp.fin_bert_scorer_service import FinBertScorerService
from domains.analytics.application.services.nlp.timeframes_service import TimeframeComputerService
from domains.analytics.application.services.ml_forecasting.daily_predictor_service import DailyPredictorService
from domains.analytics.application.services.nlp.signal_composer_service import SignalComposerService
from domains.analytics.infrastructure.adapters.outbound.redis_adapter import RedisAdapter
from domains.analytics.infrastructure.adapters.outbound.timescale_adapter import TimescaleAdapter
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_recompute")

async def test():
    cfg = get_settings()
    redis_adapter = RedisAdapter()
    store_adapter = TimescaleAdapter()
    
    deps = SubscriberDependencies(
        scorer=FinBertScorerService(),
        timeframe_computer=TimeframeComputerService(),
        predictor=DailyPredictorService(),
        composer=SignalComposerService(),
        cache=redis_adapter,
        store=store_adapter,
        publisher=redis_adapter
    )
    
    symbol = "NIFTY"
    print(f"Testing recompute for {symbol}...")
    try:
        res = await recompute_and_publish_aggregates(symbol, deps)
        print(f"Result: {res}")
    except Exception as e:
        logger.error("Test failed: %s", e, exc_info=True)

if __name__ == "__main__":
    asyncio.run(test())
