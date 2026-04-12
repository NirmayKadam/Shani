# app/Analytics/Routers/EventsRouter.py
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List

from app.Infrastructure.DatabaseClient import GetDatabasePool

Logger = logging.getLogger(__name__)
Router = APIRouter()

class EventTimelineItem(BaseModel):
    EventId: str
    EventType: str
    Headline: str
    Confidence: float
    DetectedAt: str

@Router.get("/{symbol}", response_model=List[EventTimelineItem])
async def GetEventsTimeline(
    symbol: str, 
    limit: int = Query(20, ge=1, le=100)
):
    """
    Retrieves a historical timeline of all Detected Events (like crossovers 
    and volume sweeps) for a given symbol, up to the defined limit.
    """
    SymbolUpper = symbol.upper()
    try:
        Pool = await GetDatabasePool()
        QuerySQL = """
            SELECT EventId, EventType, Headline, Confidence, DetectedAt
            FROM DetectedEvents
            WHERE Symbol = $1
            ORDER BY DetectedAt DESC
            LIMIT $2
        """
        Records = await Pool.fetch(QuerySQL, SymbolUpper, limit)
    except Exception as e:
        Logger.error(f"Postgres event timeline fetch failed for {SymbolUpper}: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")
    
    if not Records:
        return []
        
    return [
        EventTimelineItem(
            EventId=str(r["eventid"]),
            EventType=r["eventtype"],
            Headline=r["headline"] or "",
            Confidence=float(r["confidence"]),
            DetectedAt=r["detectedat"].isoformat() if r["detectedat"] else ""
        )
        for r in Records
    ]
