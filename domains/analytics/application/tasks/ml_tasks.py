"""
File Overview: Celery tasks for running multi-timeframe CNN inference and Redis cache synchronization.

All Functions/Classes:
- run_stock_prediction: Shared task for CNN inference. Data: Symbol -> Prediction results.
- update_redis: Helper to persist results. Data: Result dict -> Redis KV store.

Endpoints/APIs:
- None.

Database Tables:
- Redis (Cache).
"""
import logging

from celery import shared_task
from domains.analytics.application.services.ml_forecasting.cnn_predictor import cnn_predictor
import json
import asyncio
from shared.infrastructure.redis_client import get_redis_client
from shared.constants import RedisKeys

logger = logging.getLogger(__name__)

@shared_task(name="domains.analytics.application.tasks.ml_tasks.run_stock_prediction")
def run_stock_prediction(symbol: str):
    """Celery task to run CNN inference and update Redis read-model."""
    logger.info("[%s] Starting CNN Prediction Task", symbol)
    try:
        predictor = cnn_predictor()
        result = predictor.predict(symbol)
        
        if "error" in result:
            logger.error("[%s] Prediction failed: %s", symbol, result["error"])
            return False

        # Update Redis
        async def update_redis():
            redis = await get_redis_client()
            key = RedisKeys.ML_PREDICTION.format(symbol=symbol)
            await redis.set(key, json.dumps(result), ex=86400) # 24h TTL
            logger.info("[%s] Redis updated with prediction: %s", symbol, result["prediction"])

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            asyncio.create_task(update_redis())
        else:
            asyncio.run(update_redis())
            
        return True
    except Exception as e:
        logger.error("[%s] Unexpected error in ML task: %s", symbol, e)
        return False
