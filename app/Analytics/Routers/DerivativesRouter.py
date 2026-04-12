# app/Analytics/Routers/DerivativesRouter.py
import json
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.Infrastructure.DatabaseClient import GetDatabasePool
from app.Infrastructure.RedisClient import GetRedisClient

Logger = logging.getLogger(__name__)
Router = APIRouter()


# ── Response Models ─────────────────────────────────────────────

class IVPoint(BaseModel):
    Strike: float
    IV: float
    Type: str          # CE | PE
    Expiry: str

class PCRData(BaseModel):
    PCR: float
    CEVolume: int
    PEVolume: int
    CEOI: int
    PEOI: int
    Expiry: str

class AnomalyItem(BaseModel):
    EventId: str
    EventType: str
    Headline: str
    Confidence: float
    DetectedAt: str

class DerivativesResponse(BaseModel):
    Symbol: str
    PCR: Optional[PCRData] = None
    IVSurface: List[IVPoint] = []
    Anomalies: List[AnomalyItem] = []
    LastUpdated: str = ""


# ── Endpoint ────────────────────────────────────────────────────

@Router.get("/{symbol}", response_model=DerivativesResponse)
async def GetDerivativesSnapshot(
    symbol: str,
    anomaly_limit: int = Query(10, ge=1, le=50),
):
    """
    Returns the latest F&O analytics snapshot for a symbol:
    - Put-Call Ratio (with volume/OI breakdown)
    - Implied Volatility surface across strikes
    - Recent anomaly events (OI surges, volume sweeps)
    """
    SymbolUpper = symbol.upper()

    # 1. Fetch PCR from Redis
    PcrData_: Optional[PCRData] = None
    LastUpdated = ""
    try:
        Redis = await GetRedisClient()
        PcrStr = await Redis.get(f"derivatives:pcr:{SymbolUpper}")
        if PcrStr:
            PcrJson = json.loads(PcrStr)
            PcrData_ = PCRData(
                PCR=PcrJson.get("pcr", 0),
                CEVolume=PcrJson.get("ce_volume", 0),
                PEVolume=PcrJson.get("pe_volume", 0),
                CEOI=PcrJson.get("ce_oi", 0),
                PEOI=PcrJson.get("pe_oi", 0),
                Expiry=PcrJson.get("expiry", ""),
            )
            LastUpdated = PcrJson.get("updated_at", "")
    except Exception as e:
        Logger.error(f"Redis PCR fetch failed for {SymbolUpper}: {e}")

    # 2. Fetch IV Surface from Redis
    IvSurface: List[IVPoint] = []
    try:
        Redis = await GetRedisClient()
        IvStr = await Redis.get(f"derivatives:iv_surface:{SymbolUpper}")
        if IvStr:
            IvList = json.loads(IvStr)
            IvSurface = [
                IVPoint(
                    Strike=item.get("strike", 0),
                    IV=item.get("iv", 0),
                    Type=item.get("type", ""),
                    Expiry=item.get("expiry", ""),
                )
                for item in IvList
            ]
    except Exception as e:
        Logger.error(f"Redis IV surface fetch failed for {SymbolUpper}: {e}")

    # 3. Fetch recent anomalies from Postgres
    Anomalies: List[AnomalyItem] = []
    try:
        Pool = await GetDatabasePool()
        QuerySQL = """
            SELECT EventId, EventType, Headline, Confidence, DetectedAt
            FROM DetectedEvents
            WHERE Symbol = $1 AND EventType IN ('OI_SURGE', 'VOLUME_SWEEP')
            ORDER BY DetectedAt DESC
            LIMIT $2
        """
        Records = await Pool.fetch(QuerySQL, SymbolUpper, anomaly_limit)
        Anomalies = [
            AnomalyItem(
                EventId=str(r["eventid"]),
                EventType=r["eventtype"],
                Headline=r["headline"] or "",
                Confidence=float(r["confidence"]),
                DetectedAt=r["detectedat"].isoformat() if r["detectedat"] else "",
            )
            for r in Records
        ]
    except Exception as e:
        Logger.error(f"Postgres anomaly fetch failed for {SymbolUpper}: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

    if not PcrData_ and not IvSurface and not Anomalies:
        raise HTTPException(
            status_code=404,
            detail=f"No derivatives data available yet for {SymbolUpper}. Run tick ingestion first."
        )

    return DerivativesResponse(
        Symbol=SymbolUpper,
        PCR=PcrData_,
        IVSurface=IvSurface,
        Anomalies=Anomalies,
        LastUpdated=LastUpdated,
    )
