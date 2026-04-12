# app/Analytics/Routers/SignalsRouter.py
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.Infrastructure.DatabaseClient import GetDatabasePool
from app.Infrastructure.RedisClient import GetRedisClient

Logger = logging.getLogger(__name__)
Router = APIRouter()

class SignalResponse(BaseModel):
    Symbol: str
    CurrentEMA: float
    LatestSignal: str
    Headline: str
    DetectedAt: str

@Router.get("/{symbol}", response_model=SignalResponse)
async def GetLatestSignal(symbol: str):
    """
    Returns the real-time calculated exponential moving average (EMA) of 
    sentiment and the most recent crossover event for this symbol.
    """
    SymbolUpper = symbol.upper()
    
    # 1. Fetch current EMA from Redis fast-path
    try:
        Redis = await GetRedisClient()
        EmaStr = await Redis.get(f"signals:ema:{SymbolUpper}")
        CurrentEMA = float(EmaStr) if EmaStr else 0.0
    except Exception as e:
        Logger.error(f"Redis EMA fetch failed for {SymbolUpper}: {e}")
        CurrentEMA = 0.0

    # 2. Fetch the latest Signal Event from Postgres
    try:
        Pool = await GetDatabasePool()
        Query = """
            SELECT EventType, Headline, DetectedAt
            FROM DetectedEvents
            WHERE Symbol = $1
            ORDER BY DetectedAt DESC
            LIMIT 1
        """
        Record = await Pool.fetchrow(Query, SymbolUpper)
    except Exception as e:
        Logger.error(f"Postgres event fetch failed for {SymbolUpper}: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

    if not Record and CurrentEMA == 0.0:
        raise HTTPException(status_code=404, detail=f"No signals or exponential moving averages generated yet for {SymbolUpper}")
        
    return SignalResponse(
        Symbol=SymbolUpper,
        CurrentEMA=CurrentEMA,
        LatestSignal=Record["eventtype"] if Record else "NEUTRAL",
        Headline=Record["headline"] if Record else "No recent crossover events.",
        DetectedAt=Record["detectedat"].isoformat() if Record else "N/A"
    )
