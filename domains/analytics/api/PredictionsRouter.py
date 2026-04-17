from fastapi import APIRouter
router = APIRouter(prefix="/v1/predictions", tags=["predictions"])

@router.get("/{symbol}")
async def get_predictions(symbol: str):
    pass
