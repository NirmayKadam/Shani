# app/domain/api/routers/symbols.py — GET /v1/symbols endpoint

from fastapi import APIRouter

from app.config import GetSettings
from domains.analytics.api.schemas import SymbolsResponse

Router = APIRouter()


@Router.get("/symbols", response_model=SymbolsResponse)
async def GetSymbols():
    """
    Returns the list of recommended stock symbols.
    Frontend uses this to populate the default symbol dropdown.
    """
    cfg = GetSettings()
    symbols = cfg.GetDefaultSymbolsAsList()
    return SymbolsResponse(
        symbols=symbols,
        count=len(symbols),
        generated_at="",
        source="settings_defaults",
        stale=False,
        partial=False,
    )
