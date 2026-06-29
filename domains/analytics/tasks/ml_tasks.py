"""
File Overview: Celery tasks for running multi-timeframe CNN inference and Redis cache synchronization.

All Functions/Classes:
- run_stock_prediction: Shared task for CNN inference. Data: Symbol -> Prediction results -> Redis cache.

Endpoints/APIs: None

Database Tables:
- Redis (Cache: ml:prediction:{symbol}).
"""
import json
import logging

from celery import shared_task

from domains.analytics.application.services.ml_forecasting.cnn_predictor_service import CnnPredictorService
from shared.infrastructure.redis_client import get_redis_client_sync
from shared.constants import RedisKeys

logger = logging.getLogger(__name__)


@shared_task(name="domains.analytics.tasks.ml_tasks.run_stock_prediction")
def run_stock_prediction(symbol: str):
    """Celery task to run CNN inference and update Redis read-model."""
    logger.info("[%s] Starting CNN Prediction Task", symbol)
    try:
        predictor = CnnPredictorService()
        result = predictor.predict_sync(symbol)

        if "error" in result:
            logger.error("[%s] Prediction failed: %s", symbol, result["error"])
            return False

        # Update Redis synchronously to avoid event loop issues in Celery
        redis = get_redis_client_sync()
        key = RedisKeys.ML_PREDICTION.format(symbol=symbol)
        redis.set(key, json.dumps(result), ex=86400)  # 24h TTL
        logger.info("[%s] Redis updated with prediction: %s", symbol, result["prediction"])
        return True
    except Exception as e:
        logger.error("[%s] Unexpected error in ML task: %s", symbol, e)
        return False
