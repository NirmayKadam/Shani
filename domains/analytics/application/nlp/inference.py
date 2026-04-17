import os
import logging
import torch
import numpy as np
import pandas as pd
import yfinance as yf
from domains.analytics.application.nlp.model import QuantCNN1D

Logger = logging.getLogger(__name__)

MODEL_PATH = "/app/app/models/CNN1DPredictor.pt"
SEQ_LEN = 21

class InferenceEngine:
    _instance = None

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = QuantCNN1D(num_features=10).to(self.device)
        
        if os.path.exists(MODEL_PATH):
            try:
                self.model.load_state_dict(torch.load(MODEL_PATH, map_location=self.device))
                self.model.eval()
                self.is_loaded = True
                Logger.info("QuantCNN1D model loaded successfully for live inference.")
            except Exception as e:
                Logger.error(f"Failed to load QuantCNN1D at {MODEL_PATH}: {e}")
                self.is_loaded = False
        else:
            Logger.warning(f"CNN model weights not found at {MODEL_PATH}. Inference disabled.")
            self.is_loaded = False

    @staticmethod
    def get_instance():
        if InferenceEngine._instance is None:
            InferenceEngine._instance = InferenceEngine()
        return InferenceEngine._instance

    def _engineer_features(self, df: pd.DataFrame, live_sentiment_score: float) -> pd.DataFrame:
        if len(df) < SEQ_LEN + 15:
            return pd.DataFrame()

        df.columns = [c.lower() for c in df.columns]

        # RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["RSI_14"] = 100 - (100 / (1 + rs))
        df["RSI_14"] = df["RSI_14"] / 100.0

        # EMAs
        ema_9 = df["close"].ewm(span=9, adjust=False).mean()
        ema_21 = df["close"].ewm(span=21, adjust=False).mean()
        df["EMA9_Dist"] = (df["close"] - ema_9) / ema_9
        df["EMA21_Dist"] = (df["close"] - ema_21) / ema_21

        # Bollinger Bands
        sma_20 = df["close"].rolling(window=20).mean()
        std_20 = df["close"].rolling(window=20).std()
        bbl = sma_20 - (std_20 * 2)
        bbu = sma_20 + (std_20 * 2)
        df["BB_Width"] = (bbu - bbl) / sma_20
        df["BB_Position"] = (df["close"] - bbl) / (bbu - bbl + 1e-8)

        # Returns
        df["ret_1d"] = df["close"].pct_change(1)
        df["ret_2d"] = df["close"].pct_change(2)
        df["ret_5d"] = df["close"].pct_change(5)

        # Volume Momentum
        vol_sma_10 = df["volume"].rolling(window=10).mean()
        df["vol_momentum"] = df["volume"] / (vol_sma_10 + 1e-8)

        # Drop NaNs
        df = df.dropna()

        # Overwrite the sentiment proxy feature with the ACTUAL live FinBERT score for all latest data points
        # To maintain dimensionality we use the live sentiment score as the current context.
        df["sentiment_proxy"] = live_sentiment_score

        return df

    def predict(self, symbol: str, current_sentiment_label: str, current_sentiment_score: float) -> dict | None:
        if not self.is_loaded:
            return None
            
        try:
            from app.domain.ingestion.domain.market_data_fetcher import _to_yfinance_symbol

            # Map Indian Indices correctly for yfinance historical pulls
            yh_symbol = _to_yfinance_symbol(symbol)

            # 1. Fetch 60 days of historical daily data
            ticker = yf.Ticker(yh_symbol)
            hist = ticker.history(period="60d")
            if len(hist) < 40:
                Logger.warning(f"Not enough historical data for {symbol} inference.")
                return None
                
            # 2. Engineer features
            features_df = self._engineer_features(hist, current_sentiment_score)
            if len(features_df) < SEQ_LEN:
                return None
                
            # 3. Shape Tensor for the last 21 days
            feature_cols = ['RSI_14', 'EMA9_Dist', 'EMA21_Dist', 'BB_Width', 'BB_Position', 'ret_1d', 'ret_2d', 'ret_5d', 'vol_momentum', 'sentiment_proxy']
            recent_seq = features_df[feature_cols].values[-SEQ_LEN:]
            
            x_tensor = torch.tensor([recent_seq], dtype=torch.float32).to(self.device)
            
            # 4. Forward Pass
            with torch.no_grad():
                logits = self.model(x_tensor)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
                
            # probs[0] = Bearish, probs[1] = Bullish
            is_bullish = probs[1] > probs[0]
            prediction = "BULLISH" if is_bullish else "BEARISH"
            confidence = float(max(probs))
            
            # 5. Evaluate Confluence
            finbert_label = current_sentiment_label.upper()
            
            if finbert_label == "NEUTRAL":
                confluence = "NEUTRAL"
            elif prediction == finbert_label:
                confluence = "CONFIRMED"
            else:
                confluence = "DIVERGENT"
                
            return {
                "strategy": "QuantCNN1D",
                "prediction": prediction,
                "confidence": round(confidence, 3),
                "confluence_status": confluence,
            }
            
        except Exception as e:
            Logger.error(f"Error executing CNN inference for {symbol}: {e}")
            return None
