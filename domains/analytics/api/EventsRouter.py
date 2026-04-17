from fastapi import APIRouter
router = APIRouter(prefix="/v1/events", tags=["events"])

@router.get("/{symbol}")
async def get_events(symbol: str):
    pass
