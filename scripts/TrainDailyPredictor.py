"""
TrainDailyPredictor.py — ML Training script for Phase 5.

Usage:
    docker compose exec app python -m scripts.TrainDailyPredictor

This script downloads 5 years of daily OHLCV data for all symbols in the .env watchlist,
computes technical indicators (RSI, MACD, ATR, Bollinger Bands), and trains a
RandomForestClassifier to predict if the next day's close will be strictly higher
than today's close (Binary Classification).

The trained model is serialized saving the pipeline (imputer + scaler + random forest)
to `app/Models/DailyPredictor.joblib`.
"""

import os
import sys
import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

# Ensure the project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

Logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Configuration ───────────────────────────────────────────────

_WATCHLIST_RAW = os.getenv("WATCHLIST_SYMBOLS", "NIFTY,BANKNIFTY,RELIANCE,INFY,HDFCBANK,TCS,ICICIBANK,AXISBANK").split(",")
_WATCHLIST = [s.strip() for s in _WATCHLIST_RAW if s.strip()]

_YEARS_OF_HISTORY = 20
_MODEL_DIR = "/app/models"
_MODEL_PATH = os.path.join(_MODEL_DIR, "DailyPredictor.joblib")


def ConvertSymbolToYFinance(Symbol: str) -> str:
    """Safely map our internal symbols to yfinance `.NS` tickers."""
    SymbolUpper = Symbol.upper()
    if SymbolUpper == "NIFTY":
        return "^NSEI"
    if SymbolUpper == "BANKNIFTY":
        return "^NSEBANK"
    if SymbolUpper == "FINNIFTY":
        return "^CNXFIN"
    # For standard equities, append .NS
    if not SymbolUpper.endswith(".NS"):
        return f"{SymbolUpper}.NS"
    return SymbolUpper


def EngineerFeatures(Df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a raw DataFrame (Open, High, Low, Close, Volume),
    use pandas-ta to generate technical features.
    """
    if len(Df) < 50:
        return pd.DataFrame()  # Not enough data

    # Clean
    Df.columns = [c.lower() for c in Df.columns]
    
    # Target: 1 if Tomorrow's Close > Today's Close
    Df["target"] = (Df["close"].shift(-1) > Df["close"]).astype(int)

    # ── Pure Pandas Technical Indicators ──
    # RSI (14)
    Delta = Df["close"].diff()
    Gain = (Delta.where(Delta > 0, 0)).rolling(window=14).mean()
    Loss = (-Delta.where(Delta < 0, 0)).rolling(window=14).mean()
    RS = Gain / Loss
    Df["RSI_14"] = 100 - (100 / (1 + RS))

    # MACD (12, 26, 9)
    EMA_12 = Df["close"].ewm(span=12, adjust=False).mean()
    EMA_26 = Df["close"].ewm(span=26, adjust=False).mean()
    Df["MACD_12_26_9"] = EMA_12 - EMA_26
    Df["MACDh_12_26_9"] = Df["MACD_12_26_9"] - Df["MACD_12_26_9"].ewm(span=9, adjust=False).mean()

    # Bollinger Bands (20)
    SMA_20 = Df["close"].rolling(window=20).mean()
    STD_20 = Df["close"].rolling(window=20).std()
    Df["BBL_20_2.0"] = SMA_20 - (STD_20 * 2)
    Df["BBU_20_2.0"] = SMA_20 + (STD_20 * 2)

    # ATR (14)
    HighLow = Df["high"] - Df["low"]
    HighClose = (Df["high"] - Df["close"].shift()).abs()
    LowClose = (Df["low"] - Df["close"].shift()).abs()
    TrueRange = pd.concat([HighLow, HighClose, LowClose], axis=1).max(axis=1)
    Df["ATRr_14"] = TrueRange.rolling(window=14).mean()

    # EMAs
    Df["EMA_9"] = Df["close"].ewm(span=9, adjust=False).mean()
    Df["EMA_21"] = Df["close"].ewm(span=21, adjust=False).mean()

    # Price Lags (Returns)
    Df["ret_1d"] = Df["close"].pct_change(1)
    Df["ret_2d"] = Df["close"].pct_change(2)
    Df["ret_5d"] = Df["close"].pct_change(5)

    # Drop the last row (we don't have tomorrow's close for it yet to train on)
    Df = Df.dropna()
    return Df


def Main():
    Logger.info(f"Starting ML Training pipeline. Fetching {_YEARS_OF_HISTORY} years of data for {_WATCHLIST}")
    
    AllRows = []
    
    # ── 1. Data Collection & Feature Engineering ──
    for Sym in _WATCHLIST:
        YfSym = ConvertSymbolToYFinance(Sym)
        Logger.info(f"Downloading history for {Sym} ({YfSym})")
        
        try:
            Ticker = yf.Ticker(YfSym)
            # e.g., '5y'
            Df = Ticker.history(period=f"{_YEARS_OF_HISTORY}y")
            
            if Df.empty:
                Logger.warning(f"No data returned for {YfSym}")
                continue

            # Drop localized timezone info so we have naive datetime
            Df.index = Df.index.tz_localize(None)

            EngineeredDf = EngineerFeatures(Df.copy())
            if EngineeredDf.empty:
                Logger.warning(f"Not enough data to engineer features for {YfSym}")
                continue
                
            # Keep symbol as a feature if we want, or just combine all generic rows
            # We are building a "Universal Model" that works across all stocks
            AllRows.append(EngineeredDf)
            
        except Exception as e:
            Logger.error(f"Failed processing {YfSym}: {e}")

    if not AllRows:
        Logger.error("No data collected. Exiting.")
        sys.exit(1)

    CombinedDf = pd.concat(AllRows, axis=0)
    Logger.info(f"Final combined dataset shape: {CombinedDf.shape} rows.")

    # ── 2. Train / Test Split ──
    # Select feature columns (drop strings, targets, and dates if they are in columns)
    ExcludeCols = ["target", "open", "high", "low", "close", "volume", "dividends", "stock splits"]
    FeatureCols = [c for c in CombinedDf.columns if c not in ExcludeCols]

    X = CombinedDf[FeatureCols]
    y = CombinedDf["target"]

    Logger.info(f"Using {len(FeatureCols)} features: {FeatureCols}")

    # We use a chronological split to prevent data leakage (predicting past with future)
    # Train on oldest 80%, Test on newest 20%
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    Logger.info(f"Train size: {len(X_train)}  |  Test size: {len(X_test)}")

    # ── 3. Model Pipeline ──
    # Impute missing values -> Scale features -> Random Forest Predictor
    Pipe = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('rf', RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, class_weight="balanced"))
    ])

    Logger.info("Training RandomForestClassifier...")
    Pipe.fit(X_train, y_train)

    # ── 4. Evaluation ──
    Predictions = Pipe.predict(X_test)
    Score = accuracy_score(y_test, Predictions)
    Report = classification_report(y_test, Predictions)

    Logger.info(f"\n--- Model Evaluation (Out of Sample) ---")
    Logger.info(f"Accuracy: {Score:.4f}")
    Logger.info(f"\n{Report}")

    # ── 5. Serialization ──
    if not os.path.exists(_MODEL_DIR):
        os.makedirs(_MODEL_DIR)

    joblib.dump(Pipe, _MODEL_PATH)
    Logger.info(f"✅ Pipeline successfully serialized to {_MODEL_PATH}")

    # Also save the exact feature names the model expects
    import json
    with open(os.path.join(_MODEL_DIR, "features.json"), "w") as f:
        json.dump(FeatureCols, f)
    Logger.info("✅ Saved feature columns manifest.")


if __name__ == "__main__":
    Main()
