"""
DailyPredictor — Loading Phase 7 ML PyTorch model to generate predictions.

Runs during the Daily Prediction Celery Task (post-market close).
Fetches the last 60 days of OHLCV data for a ticker, extracts the last 21-day
sequence, generates Scale Invariant Features, and passes the 3D tensor 
through the PyTorch 1D-Convolutional Neural Network.
"""

import os
import json
import logging
from typing import Optional, Dict

import pandas as pd
import yfinance as yf
import redis.asyncio as aioredis
import torch
import torch.nn as nn
import torch.nn.functional as F

Logger = logging.getLogger(__name__)

# Constants
_MODEL_DIR = "/app/app/Models"
_MODEL_PATH = os.path.join(_MODEL_DIR, "CNN1DPredictor.pt")
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

_SEQ_LEN = 21

class QuantCNN1D(nn.Module):
    def __init__(self, num_features):
        super(QuantCNN1D, self).__init__()
        self.conv1 = nn.Conv1d(in_channels=num_features, out_channels=32, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        
        self.conv2 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1)
        self.pool2 = nn.MaxPool1d(kernel_size=2)
        
        self.adaptive_pool = nn.AdaptiveAvgPool1d(1)
        
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 2)  # Binary classification
        self.dropout = nn.Dropout(0.3)

    def forward(self, x):
        x = x.transpose(1, 2)
        x = self.conv1(x)
        x = self.relu(x)
        x = self.pool1(x)
        x = self.conv2(x)
        x = self.relu(x)
        x = self.pool2(x)
        x = self.adaptive_pool(x)
        x = x.view(x.size(0), -1)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.dropout(x)
        x = self.fc2(x)
        return x


class DailyPredictor:
    """Singleton-like loader for the ML model."""
    _Model = None
    _Device = None
    _FeatureCols = ['RSI_14', 'EMA9_Dist', 'EMA21_Dist', 'BB_Width', 'BB_Position', 'ret_1d', 'ret_2d', 'ret_5d', 'vol_momentum', 'sentiment_proxy']

    @classmethod
    def _LoadModel(cls) -> bool:
        if cls._Model is not None:
            return True

        if not os.path.exists(_MODEL_PATH):
            Logger.error("PyTorch CNN file not found! Run TrainCNNPredictor.py first.")
            return False

        try:
            cls._Device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            # We enforce exactly 9 features in the CNN constructor as declared above
            model = QuantCNN1D(num_features=len(cls._FeatureCols))
            model.load_state_dict(torch.load(_MODEL_PATH, map_location=cls._Device))
            model.to(cls._Device)
            model.eval()  # Set dropout and batchnorm to evaluation mode
            
            cls._Model = model
            Logger.info(f"✅ PyTorch 1D-CNN Model loaded successfully on {cls._Device}.")
            return True
        except Exception as e:
            Logger.error(f"Failed to load PyTorch Model: {e}")
            return False

    @staticmethod
    def _ConvertSymbol(Symbol: str) -> str:
        SymbolUpper = Symbol.upper()
        if SymbolUpper == "NIFTY": return "^NSEI"
        if SymbolUpper == "BANKNIFTY": return "^NSEBANK"
        if SymbolUpper == "FINNIFTY": return "^CNXFIN"
        if not SymbolUpper.endswith(".NS"): return f"{SymbolUpper}.NS"
        return SymbolUpper

    @classmethod
    def _EngineerFeatures(cls, Df: pd.DataFrame) -> pd.DataFrame:
        Df.columns = [c.lower() for c in Df.columns]
        
        Delta = Df["close"].diff()
        Gain = (Delta.where(Delta > 0, 0)).rolling(window=14).mean()
        Loss = (-Delta.where(Delta < 0, 0)).rolling(window=14).mean()
        RS = Gain / Loss
        Df["RSI_14"] = 100 - (100 / (1 + RS))
        Df["RSI_14"] = Df["RSI_14"] / 100.0

        EMA_9 = Df["close"].ewm(span=9, adjust=False).mean()
        EMA_21 = Df["close"].ewm(span=21, adjust=False).mean()
        Df["EMA9_Dist"] = (Df["close"] - EMA_9) / EMA_9
        Df["EMA21_Dist"] = (Df["close"] - EMA_21) / EMA_21

        SMA_20 = Df["close"].rolling(window=20).mean()
        STD_20 = Df["close"].rolling(window=20).std()
        BBL = SMA_20 - (STD_20 * 2)
        BBU = SMA_20 + (STD_20 * 2)
        Df["BB_Width"] = (BBU - BBL) / SMA_20
        Df["BB_Position"] = (Df["close"] - BBL) / (BBU - BBL + 1e-8)

        Df["ret_1d"] = Df["close"].pct_change(1)
        Df["ret_2d"] = Df["close"].pct_change(2)
        Df["ret_5d"] = Df["close"].pct_change(5)

        Vol_SMA_10 = Df["volume"].rolling(window=10).mean()
        Df["vol_momentum"] = Df["volume"] / (Vol_SMA_10 + 1e-8)

        # Sentiment proxy: contrarian mean-reversion signal
        # This gets overridden with the live EMA sentiment from Redis during inference
        Df["sentiment_proxy"] = (-Df["ret_5d"]).ewm(span=10, adjust=False).mean()

        return Df.dropna()

    @classmethod
    async def PredictNextDay(cls, Symbol: str) -> Optional[Dict]:
        """
        Fetch latest data, extract the 21-day scale-invariant sequence, and perform forward inference.
        """
        if not cls._LoadModel():
            return None

        YfSym = cls._ConvertSymbol(Symbol)
        Logger.info(f"[{Symbol}] Fetching data for CNN Inference...")

        try:
            Ticker = yf.Ticker(YfSym)
            Df = Ticker.history(period="60d")

            if Df.empty or len(Df) < 30:
                return None

            Df.index = Df.index.tz_localize(None)
            EngineeredDf = cls._EngineerFeatures(Df)
            
            if len(EngineeredDf) < _SEQ_LEN:
                Logger.warning(f"[{Symbol}] Not enough contiguous clean data to form a {_SEQ_LEN}-day sequence.")
                return None

            # Inject live EMA sentiment from Redis into the last row
            # This gives the model real FinBERT NLP sentiment for today's prediction
            try:
                SentimentRedis = aioredis.from_url(_REDIS_URL, decode_responses=True)
                EmaStr = await SentimentRedis.get(f"signals:ema:{Symbol.upper()}")
                await SentimentRedis.aclose()
                if EmaStr:
                    LiveSentiment = float(EmaStr)
                    EngineeredDf.loc[EngineeredDf.index[-1], 'sentiment_proxy'] = LiveSentiment
                    Logger.info(f"[{Symbol}] Injected live EMA sentiment: {LiveSentiment:.4f}")
            except Exception as SentErr:
                Logger.debug(f"[{Symbol}] Could not fetch live sentiment, using proxy: {SentErr}")

            # Extract precisely the last 21 rows
            SequenceDf = EngineeredDf.iloc[-_SEQ_LEN:]
            X_infer_np = SequenceDf[cls._FeatureCols].values
            
            # Reshape into PyTorch 3D Tensor: (Batch=1, Seq_Len=21, Features=9)
            X_tensor = torch.tensor([X_infer_np], dtype=torch.float32).to(cls._Device)

            # PyTorch Forward Pass
            with torch.no_grad():
                logits = cls._Model(X_tensor)
                # Apply Softmax to get probabilities [0.0 to 1.0]
                probabilities = F.softmax(logits, dim=1).cpu().numpy()[0]
                
            ProbDown = float(probabilities[0])
            ProbUp = float(probabilities[1])
            PredictedClass = 1 if ProbUp > ProbDown else 0

            Result = {
                "symbol": Symbol.upper(),
                "prediction": "BULLISH" if PredictedClass == 1 else "BEARISH",
                "up_probability": round(ProbUp, 4),
                "down_probability": round(ProbDown, 4),
                "last_close": float(SequenceDf["close"].iloc[-1]),
                "date": SequenceDf.index[-1].strftime("%Y-%m-%d"),
            }

            Logger.info(f"[{Symbol}] 🌟 CNN AI Prediction: {Result['prediction']} ({(ProbUp*100):.1f}%)")

            # Cache to Redis
            Redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
            await Redis.set(f"ml:prediction:{Symbol.upper()}", json.dumps(Result), ex=86400)
            await Redis.aclose()

            return Result

        except Exception as e:
            Logger.error(f"[{Symbol}] CNN Inference error: {e}")
            return None
