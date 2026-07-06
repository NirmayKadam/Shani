import os
import pytest
import numpy as np
import pandas as pd
import torch
from unittest.mock import MagicMock, patch

from domains.analytics.application.services.nlp.model import QuantCNN1D
from domains.analytics.application.services.nlp.inference import InferenceEngine

@pytest.mark.unit
def test_quant_cnn_model_forward():
    batch_size = 4
    seq_len = 21
    num_features = 12
    
    model = QuantCNN1D(num_features=num_features)
    x = torch.randn(batch_size, seq_len, num_features)
    out = model(x)
    
    assert out.shape == (batch_size, 1)


@pytest.mark.unit
def test_inference_engine_feature_engineering():
    # Setup dummy OHLCV data
    dates = pd.date_range(start="2026-01-01", periods=160, freq="h")
    np.random.seed(42)
    df = pd.DataFrame({
        "Open": np.random.uniform(100, 110, 160),
        "High": np.random.uniform(110, 120, 160),
        "Low": np.random.uniform(90, 100, 160),
        "Close": np.random.uniform(100, 110, 160),
        "Volume": np.random.randint(1000, 5000, 160)
    }, index=dates)
    
    # Load inference engine with mocked model loading to avoid needing PT file
    with patch("os.path.exists", return_value=False):
        engine = InferenceEngine()
        
    engineered = engine._engineer_features(df)
    assert not engineered.empty
    
    expected_cols = [
        'RSI_14', 'EMA9_Dist', 'EMA21_Dist', 'EMA50_Dist', 'EMA100_Dist',
        'BB_Width', 'BB_Position', 'MACD_Dist', 'P_Dist', 'R1_Dist', 'S1_Dist', 'vol_momentum'
    ]
    for col in expected_cols:
        assert col in engineered.columns


@pytest.mark.unit
@patch("domains.analytics.application.services.nlp.inference.yf")
def test_inference_engine_predict_success(mock_yf):
    # Initialize engine with mock loading to avoid loading weight errors
    with patch("os.path.exists", return_value=False):
        engine = InferenceEngine()
        
    # Mock internal model to return fixed value
    mock_model = MagicMock()
    mock_model.return_value = torch.tensor([[0.015]]) # +1.5% predicted return
    engine.model = mock_model
    engine.is_loaded = True
    
    # Dummy data frame with fluctuations to prevent NaNs in RSI/BB calculations
    dates = pd.date_range(start="2026-01-01", periods=160, freq="h")
    np.random.seed(42)
    df = pd.DataFrame({
        "Open": np.random.uniform(100, 110, 160),
        "High": np.random.uniform(110, 120, 160),
        "Low": np.random.uniform(90, 100, 160),
        "Close": np.random.uniform(100, 110, 160),
        "Volume": np.random.randint(1000, 5000, 160)
    }, index=dates)
    
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    mock_yf.Ticker.return_value = mock_ticker
    
    result = engine.predict("RELIANCE", interval="1h")
    
    assert result is not None
    assert result["strategy"] == "QuantCNN1D"
    assert result["predicted_return"] == 0.015
    assert result["direction"] == "UP"
