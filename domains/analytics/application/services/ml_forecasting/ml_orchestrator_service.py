"""
File Overview: MLOrchestratorService coordinates technical feature engineering and CNN-LSTM volatility forecasting.
"""
import logging
from typing import Dict, Any, Optional

from domains.analytics.application.services.ml_forecasting.feature_engineer_service import FeatureEngineerService
from domains.analytics.application.services.ml_forecasting.cnn_predictor_service import CnnPredictorService

logger = logging.getLogger(__name__)

class MLOrchestratorService:
    def __init__(self, predictor: Optional[CnnPredictorService] = None, feature_engineer: Optional[FeatureEngineerService] = None):
        self._predictor = predictor or CnnPredictorService()
        self._feature_engineer = feature_engineer or FeatureEngineerService()

    async def run_pipeline(self, symbol: str) -> Dict[str, Any]:
        """
        Runs the feature engineering and model inference for the given symbol.
        """
        logger.info("[%s] ML Orchestrator executing volatility prediction pipeline", symbol)
        try:
            prediction_result = await self._predictor.predict(symbol)
            if "error" in prediction_result:
                logger.error("[%s] Volatility prediction pipeline failed: %s", symbol, prediction_result["error"])
            else:
                logger.info("[%s] Volatility prediction pipeline completed successfully", symbol)
            return prediction_result
        except Exception as exc:
            logger.exception("[%s] Unexpected exception during prediction orchestration", symbol)
            return {"error": str(exc)}
