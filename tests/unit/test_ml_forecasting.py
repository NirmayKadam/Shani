import sys
from unittest.mock import MagicMock, patch, AsyncMock
if 'torch' in sys.modules and (isinstance(sys.modules['torch'], MagicMock) or 'MagicMock' in str(type(sys.modules['torch']))):
    for m in list(sys.modules.keys()):
        if m == 'torch' or m.startswith('torch.'):
            del sys.modules[m]

import pytest
import pandas as pd
import numpy as np
import torch
from domains.analytics.application.services.ml_forecasting.feature_engineer_service import FeatureEngineerService
from domains.analytics.application.services.ml_forecasting.ml_orchestrator_service import MLOrchestratorService
from domains.analytics.application.services.ml_forecasting.cnn_predictor_service import CnnPredictorService

@pytest.mark.unit
class TestFeatureEngineerService:
    def test_engineer_features_success(self):
        # Create a dummy DataFrame with enough rows (>= 60) for technical indicators
        dates = pd.date_range(start="2026-01-01", periods=100, freq="D")
        np.random.seed(42)
        df = pd.DataFrame({
            "Open": np.random.uniform(100, 110, 100),
            "High": np.random.uniform(110, 120, 100),
            "Low": np.random.uniform(90, 100, 100),
            "Close": np.random.uniform(100, 110, 100),
            "Volume": np.random.randint(1000, 5000, 100)
        }, index=dates)
        
        fe = FeatureEngineerService()
        result = fe.engineer_features(df)
        
        # Verify calculated indicators exist and are not empty
        assert not result.empty
        assert "RSI_14" in result.columns
        assert "MACD" in result.columns
        assert "MACD_Signal" in result.columns
        assert "MACD_Hist" in result.columns
        assert "Stoch_K" in result.columns
        assert "Stoch_D" in result.columns
        assert "Williams_R" in result.columns
        assert "EMA9_Dist" in result.columns
        assert "EMA21_Dist" in result.columns
        assert "EMA50_Dist" in result.columns
        assert "ADX" in result.columns
        assert "BB_Width" in result.columns
        assert "BB_Position" in result.columns
        assert "ATR_Norm" in result.columns
        assert "ret_1d" in result.columns
        assert "ret_5d" in result.columns
        assert "ret_10d" in result.columns
        assert "HL_Ratio" in result.columns
        assert "OC_Ratio" in result.columns
        assert "Gap" in result.columns
        assert "vol_momentum" in result.columns
        assert "OBV_Norm" in result.columns

    def test_engineer_features_insufficient_data(self):
        # Dataframe with < 60 rows should return empty dataframe
        df = pd.DataFrame({
            "Close": [100.0] * 10
        })
        fe = FeatureEngineerService()
        result = fe.engineer_features(df)
        assert result.empty

@pytest.mark.unit
class TestMLOrchestratorService:
    @pytest.mark.asyncio
    async def test_run_pipeline_success(self):
        mock_predictor = MagicMock(spec=CnnPredictorService)
        mock_predictor.predict = AsyncMock(return_value={
            "symbol": "NIFTY",
            "strategy": "MTF-CNN-LSTM-VOL",
            "prediction": "VOL_CRUSH",
            "confidence": 0.85,
            "confluence_status": "HIGH"
        })
        
        orchestrator = MLOrchestratorService(predictor=mock_predictor)
        result = await orchestrator.run_pipeline("NIFTY")
        
        assert result["symbol"] == "NIFTY"
        assert result["prediction"] == "VOL_CRUSH"
        assert result["confidence"] == 0.85
        mock_predictor.predict.assert_called_once_with("NIFTY")

    @pytest.mark.asyncio
    async def test_run_pipeline_error(self):
        mock_predictor = MagicMock(spec=CnnPredictorService)
        mock_predictor.predict = AsyncMock(return_value={"error": "Inference failed"})
        
        orchestrator = MLOrchestratorService(predictor=mock_predictor)
        result = await orchestrator.run_pipeline("NIFTY")
        
        assert "error" in result
        assert result["error"] == "Inference failed"

@pytest.mark.unit
class TestCnnPredictorServiceWithMocks:
    @pytest.mark.asyncio
    @patch("domains.analytics.application.services.ml_forecasting.cnn_predictor_service.MultiTimeframeCNN")
    @patch("domains.analytics.application.services.ml_forecasting.cnn_predictor_service.torch")
    @patch("domains.analytics.application.services.ml_forecasting.cnn_predictor_service.yf")
    @patch("domains.analytics.application.services.ml_forecasting.cnn_predictor_service.os.path.exists")
    async def test_predict_success(self, mock_exists, mock_yf, mock_torch, mock_cnn_class):
        # 1. Setup mocks for model load
        mock_exists.return_value = True
        
        mock_scaler = MagicMock()
        mock_scaler.transform.side_effect = lambda x: x # Identity transform
        
        mock_checkpoint = {
            'model': {},
            'scalers': {
                'daily': mock_scaler,
                'weekly': mock_scaler,
                'monthly': mock_scaler
            }
        }
        mock_torch.load.return_value = mock_checkpoint

        # 2. Setup mock yfinance Ticker history dataframes
        np.random.seed(42)
        dates_daily = pd.date_range(start="2026-01-01", periods=100, freq="D")
        df_daily = pd.DataFrame({
            "Open": np.random.uniform(100, 110, 100),
            "High": np.random.uniform(110, 120, 100),
            "Low": np.random.uniform(90, 100, 100),
            "Close": np.random.uniform(100, 110, 100),
            "Volume": np.random.randint(1000, 5000, 100)
        }, index=dates_daily)

        dates_weekly = pd.date_range(start="2025-01-01", periods=65, freq="W")
        df_weekly = pd.DataFrame({
            "Open": np.random.uniform(100, 110, 65),
            "High": np.random.uniform(110, 120, 65),
            "Low": np.random.uniform(90, 100, 65),
            "Close": np.random.uniform(100, 110, 65),
            "Volume": np.random.randint(1000, 5000, 65)
        }, index=dates_weekly)

        dates_monthly = pd.date_range(start="2020-01-01", periods=65, freq="M")
        df_monthly = pd.DataFrame({
            "Open": np.random.uniform(100, 110, 65),
            "High": np.random.uniform(110, 120, 65),
            "Low": np.random.uniform(90, 100, 65),
            "Close": np.random.uniform(100, 110, 65),
            "Volume": np.random.randint(1000, 5000, 65)
        }, index=dates_monthly)

        # Mock ticker instances
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = [df_daily, df_weekly, df_monthly]
        
        mock_vix_ticker = MagicMock()
        mock_vix_ticker.history.side_effect = [
            pd.DataFrame({"Close": np.random.uniform(12, 18, 100)}, index=dates_daily),
            pd.DataFrame({"Close": np.random.uniform(12, 18, 65)}, index=dates_weekly),
            pd.DataFrame({"Close": np.random.uniform(12, 18, 65)}, index=dates_monthly)
        ]

        mock_tnx_ticker = MagicMock()
        mock_tnx_ticker.history.side_effect = [
            pd.DataFrame({"Close": np.random.uniform(3.5, 4.5, 100)}, index=dates_daily),
            pd.DataFrame({"Close": np.random.uniform(3.5, 4.5, 65)}, index=dates_weekly),
            pd.DataFrame({"Close": np.random.uniform(3.5, 4.5, 65)}, index=dates_monthly)
        ]

        mock_dxy_ticker = MagicMock()
        mock_dxy_ticker.history.side_effect = [
            pd.DataFrame({"Close": np.random.uniform(100, 105, 100)}, index=dates_daily),
            pd.DataFrame({"Close": np.random.uniform(100, 105, 65)}, index=dates_weekly),
            pd.DataFrame({"Close": np.random.uniform(100, 105, 65)}, index=dates_monthly)
        ]

        mock_yf.Ticker.side_effect = lambda sym: {
            "NIFTY": mock_ticker,
            "^VIX": mock_vix_ticker,
            "^TNX": mock_tnx_ticker,
            "DX-Y.NYB": mock_dxy_ticker
        }.get(sym, mock_ticker)

        # Initialize predictor service
        predictor = CnnPredictorService()
        
        # Override the neural network and torch operations inside _run_forward
        predictor.model = MagicMock()
        mock_logits = MagicMock()
        predictor.model.return_value = mock_logits
        
        mock_probs = MagicMock()
        mock_pred_idx = MagicMock()
        
        mock_torch.softmax.return_value = mock_probs
        mock_torch.argmax.return_value = mock_pred_idx
        
        mock_pred_idx.item.return_value = 1 # Neutral class is index 1
        mock_probs.__getitem__.return_value.__getitem__.return_value.item.return_value = 0.8
        
        # Run predict
        result = await predictor.predict("NIFTY")
        
        # Validate predictions and macro metrics
        assert result["symbol"] == "NIFTY"
        assert result["prediction"] == "NEUTRAL"
        assert "macro_vix" in result
        assert "macro_tnx_mom" in result
        assert "macro_dxy_ret" in result

