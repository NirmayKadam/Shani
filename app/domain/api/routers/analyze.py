# app/domain/api/routers/analyze.py — GET /v1/analyze/{symbol} endpoint

import logging
from fastapi import APIRouter, HTTPException

from app.config import GetSettings
from app.domain.api.schemas import AnalysisResponse

Logger = logging.getLogger(__name__)

Router = APIRouter()


@Router.get("/analyze/{symbol}", response_model=AnalysisResponse)
async def AnalyzeSymbol(symbol: str):
    """
    Cache-first analysis endpoint.

    Behavior:
      1. Reads latest Redis/Postgres read-model snapshot.
      2. Returns freshness metadata (`generated_at`, `stale`, `partial`).
      3. Enqueues background refresh when snapshot is stale/partial.

    Heavy fetch + NLP scoring is intentionally performed in worker flows,
    not in the request thread.
    """
    symbol_upper = symbol.strip().upper()

    # Validate symbol is in the watchlist
    cfg = GetSettings()
    allowed = cfg.GetWatchlistAsList()
    if symbol_upper not in allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Symbol '{symbol_upper}' is not in the watchlist.",
                "allowed_symbols": allowed,
                "hint": "Use GET /v1/symbols to see available symbols.",
            },
        )

    try:
        from app.domain.api.services.analysis_service import AnalysisService

        service = AnalysisService()
        return await service.analyze(symbol_upper)
    except Exception as exc:
        Logger.error("[%s] Analysis failed: %s", symbol_upper, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed for {symbol_upper}. Please try again. Error: {str(exc)}",
        )
