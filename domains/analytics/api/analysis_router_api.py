"""
File Overview: FastAPI router for the /v1/analyze/{symbol} endpoint, providing a cache-first analysis view.

All Functions/Classes:
- _generated_at: Internal helper for UTC timestamps. Take current system time and send ISO string.
- _error_envelope: Standardized error dictionary builder. Take error/code/details and send error dict.
- _get_service: Lazy-initialization singleton for AnalysisService. Take class definition and send instance.
- AnalyzeSymbol: Primary GET endpoint for full-page analytics. Take symbol from path and send AnalysisResponse from AnalysisService.

Endpoints/APIs:
- GET /analyze/{symbol}.

Database Tables:
- None.
"""
# domains/analytics/api/analysis_router.py — GET /v1/analyze/{symbol} endpoint
# NOTE: This router is named sentiment_router for historical reasons.
# It serves the /analyze/{symbol} endpoint using AnalysisService.


import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from domains.analytics.api.schemas import AnalysisResponse

logger = logging.getLogger(__name__)

router = APIRouter()
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
        from domains.analytics.application.services.analysis_service import AnalysisService
        _Service = AnalysisService()
    return _Service


@router.get("/analyze/{symbol}", response_model=AnalysisResponse)
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

    # Validate symbol format and existence
    from shared.utils.symbol_validator import SymbolValidator
    if not SymbolValidator.validate(symbol_upper):
        raise HTTPException(
            status_code=400,
            detail=_error_envelope(
                error=f"Symbol '{symbol_upper}' is invalid or not supported.",
                code="invalid_symbol",
                details={
                    "hint": "Ensure the ticker is correct (e.g., RELIANCE or AAPL). Use .NS suffix for Indian stocks if needed.",
                },
            ),
        )

    symbol_clean = SymbolValidator.get_clean_symbol(symbol_upper)

    try:
        service = _get_service()
        # Use symbol_clean (canonical) for generic analysis read models.
        # Downstream predictors will handle yfinance specific cleaning if needed.
        return await service.analyze(symbol_clean)
    except Exception as exc:
        logger.error("[%s] Analysis failed: %s", symbol_upper, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=_error_envelope(
                error=f"Analysis failed for {symbol_upper}. Please try again.",
                code="analysis_runtime_failure",
                details={"exception": str(exc)},
            ),
        )
