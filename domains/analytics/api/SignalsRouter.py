from fastapi import APIRouter
router = APIRouter(prefix="/signals", tags=["signals"])

@router.get("/{symbol}")
async def get_signals(symbol: str):
    pass
