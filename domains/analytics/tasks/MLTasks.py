import logging
from celery import shared_task
from domains.analytics.application.ml_forecasting.CNNPredictor import CNNPredictor
import json
import asyncio
from app.shared.redis_client import GetRedisClient
from app.shared.constants import RedisKeys

Logger = logging.getLogger(__name__)

@shared_task(name="domains.analytics.tasks.MLTasks.run_stock_prediction")
def run_stock_prediction(symbol: str):
    """Celery task to run CNN inference and update Redis read-model."""
    Logger.info("[%s] Starting CNN Prediction Task", symbol)
    try:
        predictor = CNNPredictor()
        result = predictor.predict(symbol)
        
        if "error" in result:
            Logger.error("[%s] Prediction failed: %s", symbol, result["error"])
            return False

        # Update Redis
        async def update_redis():
            redis = await GetRedisClient()
            key = RedisKeys.ML_PREDICTION.format(symbol=symbol)
            await redis.set(key, json.dumps(result), ex=86400) # 24h TTL
            Logger.info("[%s] Redis updated with prediction: %s", symbol, result["prediction"])

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(update_redis())
        else:
            asyncio.run(update_redis())
            
        return True
    except Exception as e:
        Logger.error("[%s] Unexpected error in ML task: %s", symbol, e)
        return False
