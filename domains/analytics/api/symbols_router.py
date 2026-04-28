"""
File Overview: FastAPI router for the /v1/symbols endpoint, providing a list of recommended symbols from application settings.

All Functions/Classes:
- GetSymbols: FastAPI GET endpoint. Take default symbols from settings and send SymbolsResponse.

Endpoints/APIs:
- GET /symbols.

Database Tables:
- None.
"""
# app/domain/api/routers/symbols.py — GET /v1/symbols endpoint


from fastapi import APIRouter

from app.config import get_settings
from domains.analytics.api.schemas import SymbolsResponse

Router = APIRouter()


@Router.get("/symbols", response_model=SymbolsResponse)
async def GetSymbols():
    """
    Returns the list of recommended stock symbols.
    Frontend uses this to populate the default symbol dropdown.
    """
    cfg = get_settings()
    symbols = cfg.get_default_symbols_as_list()
    return SymbolsResponse(
        symbols=symbols,
        count=len(symbols),
        generated_at="",
        source="settings_defaults",
        stale=False,
        partial=False,
    )
