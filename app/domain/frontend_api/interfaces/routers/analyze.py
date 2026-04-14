# app/domain/api/routers/analyze.py — GET /v1/analyze/{symbol} endpoint

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import GetSettings
from app.domain.frontend_api.interfaces.schemas import AnalysisResponse

Logger = logging.getLogger(__name__)

Router = APIRouter()
_Service = None


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_envelope(*, error: str, code: str, details=None) -> dict:
    return {
        "generated_at": _generated_at(),
        "source": "frontend_api",
        "stale": False,
        "partial": True,
        "error": error,
        "code": code,
        "details": details,
    }


def _get_service():
    global _Service
    if _Service is None:
        from app.domain.frontend_api.application.services.analysis_service import AnalysisService
        _Service = AnalysisService()
    return _Service


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
            detail=_error_envelope(
                error=f"Symbol '{symbol_upper}' is not in the watchlist.",
                code="invalid_symbol",
                details={
                    "allowed_symbols": allowed,
                    "hint": "Use GET /v1/symbols to see available symbols.",
                },
            ),
        )

    try:
        service = _get_service()
        return await service.analyze(symbol_upper)
    except Exception as exc:
        Logger.error("[%s] Analysis failed: %s", symbol_upper, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_envelope(
                error=f"Analysis failed for {symbol_upper}. Please try again.",
                code="analysis_runtime_failure",
                details={"exception": str(exc)},
            ),
        )
