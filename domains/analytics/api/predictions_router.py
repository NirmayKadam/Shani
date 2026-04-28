"""
File Overview: FastAPI router for retrieving ML volatility predictions from the CNN model.

All Functions/Classes:
- _get_predictor: Helper to lazy-initialize the global cnn_predictor instance. Take predictor class and send instance.
- get_predictions: GET endpoint for ML forecasts. Take symbol from path and send prediction results from CNN model.

Endpoints/APIs:
- GET /predictions/{symbol}.

Database Tables:
- None.
"""
import logging

from fastapi import APIRouter, HTTPException
from domains.analytics.application.services.ml_forecasting.cnn_predictor import cnn_predictor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])
_predictor = None


def _get_predictor():
    global _predictor
    if _predictor is None:
        _predictor = cnn_predictor()
    return _predictor


@router.get("/{symbol}")
async def get_predictions(symbol: str):
    try:
        predictor = _get_predictor()
    except Exception as e:
        logger.error("Failed to load CNN model: %s", e)
        raise HTTPException(status_code=503, detail=f"Prediction model not initialized: {e}")

    result = predictor.predict(symbol)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result
