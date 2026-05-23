"""
File Overview: Application service for daily market volatility predictions.
Wraps the CnnPredictorService to provide domain-aligned forecasting.
"""

import logging
from typing import Dict, Any, Optional
from domains.analytics.application.services.ml_forecasting.cnn_predictor_service import CnnPredictorService

logger = logging.getLogger(__name__)

class DailyPredictorService:
    """
    Application service that generates daily volatility and trend forecasts.
    """

    def __init__(self, model_path: Optional[str] = None):
        if model_path:
            self._predictor = CnnPredictorService(model_path=model_path)
        else:
            self._predictor = CnnPredictorService()

    async def generate_prediction(self, symbol: str) -> Dict[str, Any]:
        """
        Generate a multi-timeframe prediction for a symbol.
        
        Output format matches CnnPredictorService.predict:
        {
            "symbol": str,
            "strategy": "MTF-CNN-LSTM-VOL",
            "prediction": "VOL_CRUSH" | "NEUTRAL" | "VOL_EXPAND",
            "confidence": float,
            "confluence_status": "HIGH" | "MODERATE" | "LOW"
        }
        """
        try:
            logger.info("[%s] Generating daily prediction...", symbol)
            result = await self._predictor.predict(symbol)
            
            if "error" in result:
                logger.error("[%s] Prediction error: %s", symbol, result["error"])
                return {
                    "symbol": symbol,
                    "prediction": "NEUTRAL",
                    "confidence": 0.0,
                    "confluence_status": "LOW",
                    "error": result["error"]
                }
                
            return result
        except Exception as exc:
            logger.error("[%s] Failed to generate prediction: %s", symbol, exc)
            return {
                "symbol": symbol,
                "prediction": "NEUTRAL",
                "confidence": 0.0,
                "confluence_status": "LOW"
            }
