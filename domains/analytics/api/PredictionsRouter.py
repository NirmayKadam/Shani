import logging
from fastapi import APIRouter, HTTPException
from domains.analytics.application.ml_forecasting.CNNPredictor import CNNPredictor

Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])
_predictor = None


def _get_predictor():
    global _predictor
    if _predictor is None:
        _predictor = CNNPredictor()
    return _predictor


@router.get("/{symbol}")
async def get_predictions(symbol: str):
    try:
        predictor = _get_predictor()
    except Exception as e:
        Logger.error("Failed to load CNN model: %s", e)
        raise HTTPException(status_code=503, detail=f"Prediction model not initialized: {e}")

    result = predictor.predict(symbol)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result
