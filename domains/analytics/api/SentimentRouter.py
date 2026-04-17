from fastapi import APIRouter
router = APIRouter(prefix="/v1/sentiment", tags=["sentiment"])

@router.get("/{symbol}")
async def get_sentiment(symbol: str):
    # TODO: reads from ICache only
    pass
