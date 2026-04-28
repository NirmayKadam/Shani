"""
File Overview: FastAPI router for derivatives-related analytics endpoints.

All Functions/Classes:
- get_derivatives: FastAPI GET endpoint. Take symbol from path and send placeholder response.

Endpoints/APIs:
- GET /v1/derivatives/{symbol}.

Database Tables:
- None.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/v1/derivatives", tags=["derivatives"])


@router.get("/{symbol}")
async def get_derivatives(symbol: str):
    pass
