# app/Analytics/Routers/SentimentRouter.py
import json
import logging
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from typing import Optional

from app.Infrastructure.RedisClient import GetRedisClient
from app.Infrastructure.DatabaseClient import GetDatabasePool

Logger = logging.getLogger(__name__)

Router = APIRouter()

class SentimentResponse(BaseModel):
    Symbol: str
    Label: str
    Score: float
    Headline: str
    Timestamp: str
    Source: str

@Router.get("/{symbol}", response_model=SentimentResponse)
async def GetLatestSentiment(
    symbol: str = Path(..., title="The stock symbol to query", min_length=1)
):
    """
    Get the latest sentiment for a given stock symbol.
    Extremely fast <100ms: Tries Redis hot-cache first, falls back to PostgreSQL.
    """
    SymbolUpper = symbol.upper()
    
    # 1. Try Redis Hot Path
    try:
        Redis = await GetRedisClient()
        CacheKey = f"sentiment:{SymbolUpper}:latest"
        CachedData = await Redis.get(CacheKey)
        
        if CachedData:
            Parsed = json.loads(CachedData)
            return SentimentResponse(
                Symbol=Parsed.get("Symbol", SymbolUpper),
                Label=Parsed.get("Label", "NEUTRAL"),
                Score=float(Parsed.get("Score", 0.0)),
                Headline=Parsed.get("Headline", ""),
                Timestamp=str(Parsed.get("Timestamp", "")),
                Source=Parsed.get("Source", "")
            )
    except Exception as Exc:
        Logger.error(f"Redis cache read failed for {SymbolUpper}: {Exc} - falling back to DB")
        # Proceed to DB fallback

    # 2. Try PostgreSQL Fallback
    try:
        Pool = await GetDatabasePool()
        Query = """
            SELECT Symbol, SentimentLabel, SentimentScore, Headline, CreatedAt, SourceUrl
            FROM SentimentScores
            WHERE Symbol = $1 AND SentimentLabel != 'PENDING'
            ORDER BY CreatedAt DESC
            LIMIT 1
        """
        Record = await Pool.fetchrow(Query, SymbolUpper)
        
        if Record:
            return SentimentResponse(
                Symbol=Record["symbol"],
                Label=Record["sentimentlabel"],
                Score=float(Record["sentimentscore"]),
                Headline=Record["headline"] or "",
                Timestamp=Record["createdat"].isoformat() if Record["createdat"] else "",
                Source=Record["sourceurl"] or ""
            )
    except Exception as Exc:
        Logger.error(f"Database read failed for {SymbolUpper}: {Exc}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching sentiment data.")

    # 3. Not found anywhere
    raise HTTPException(status_code=404, detail=f"No sentiment data found for symbol: {SymbolUpper}")
