# app/Analytics/Routers/PredictionsRouter.py
import json
import logging
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

from app.Infrastructure.RedisClient import GetRedisClient

Logger = logging.getLogger(__name__)
Router = APIRouter()

class PredictionResponse(BaseModel):
    Symbol: str
    Prediction: str         # BULLISH | BEARISH
    UpProbability: float
    DownProbability: float
    LastClose: float
    Date: str

@Router.get("/{symbol}", response_model=PredictionResponse)
async def GetLatestPrediction(symbol: str):
    """
    Returns the latest End-Of-Day daily forecast from the Machine Learning predictor.
    Updates every day at 3:45 PM IST.
    """
    SymbolUpper = symbol.upper()
    Redis = await GetRedisClient()

    PredStr = await Redis.get(f"ml:prediction:{SymbolUpper}")
    if not PredStr:
        raise HTTPException(
            status_code=404,
            detail=f"No prediction found for {SymbolUpper}. The daily prediction task may not have run yet."
        )

    try:
        Data = json.loads(PredStr)
        return PredictionResponse(
            Symbol=Data.get("symbol", SymbolUpper),
            Prediction=Data.get("prediction", "UNKNOWN"),
            UpProbability=Data.get("up_probability", 0.0),
            DownProbability=Data.get("down_probability", 0.0),
            LastClose=Data.get("last_close", 0.0),
            Date=Data.get("date", ""),
        )
    except Exception as e:
        Logger.error(f"Failed to parse ML prediction from Redis for {SymbolUpper}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error parsing prediction data")
