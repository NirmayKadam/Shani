# app/domain/api/routers/symbols.py — GET /v1/symbols endpoint

from fastapi import APIRouter

from app.config import GetSettings
from domains.analytics.api.schemas import SymbolsResponse

Router = APIRouter()


@Router.get("/symbols", response_model=SymbolsResponse)
async def GetSymbols():
    """
    Returns the list of available watchlist symbols.
    Frontend uses this to populate the symbol dropdown.
    """
    cfg = GetSettings()
    symbols = cfg.GetWatchlistAsList()
    return SymbolsResponse(
        symbols=symbols,
        count=len(symbols),
        generated_at="",
        source="settings_watchlist",
        stale=False,
        partial=False,
    )
