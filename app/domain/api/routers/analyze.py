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
    On-demand full analysis for a stock symbol.

    Orchestrates:
      1. Fetch current/last-close market data (yfinance)
      2. Fetch latest 20 headlines (NewsAPI)
      3. Score all headlines with FinBERT NLP
      4. Compute multi-timeframe sentiment (intraday/daily/weekly/monthly)
      5. Fetch option chain + compute PCR

    Always returns data — even when market is closed (uses last-close price).

    Note: First request may take ~15-20s due to FinBERT model loading.
    Subsequent requests are fast (<3s).
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

    # Run the full analysis pipeline
    try:
        from app.domain.api.services.analysis_service import AnalysisService
        service = AnalysisService()
        result = await service.analyze(symbol_upper)
        return result

    except Exception as exc:
        Logger.error("[%s] Analysis failed: %s", symbol_upper, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed for {symbol_upper}. Please try again. Error: {str(exc)}",
        )
