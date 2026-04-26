from fastapi import APIRouter
router = APIRouter(prefix="/v1/derivatives", tags=["derivatives"])

@router.get("/{symbol}")
async def get_derivatives(symbol: str):
    pass
