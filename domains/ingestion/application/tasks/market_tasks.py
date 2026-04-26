import json
import logging
import asyncio
import httpx
from celery import shared_task
from shared.infrastructure.redis_client import get_redis_sync
from urllib.parse import quote

logger = logging.getLogger(__name__)

async def _fetch_and_publish_options_async(symbol: str):
    redis = get_redis_sync()
    
    # Internal NSE API Wrapper Endpoint
    api_url = f"http://127.0.0.1:8000/v1/ingestion/options/{quote(symbol)}"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()
            
        S0 = data.get("underlying_value", 0)
        raw = data.get("raw_chain", [])
        
        # Calculate roughly +/- 10% strikes around spot price for PDE solving
        strikes = []
        for strike_data in raw:
            st = strike_data.get("strikePrice")
            if st and S0 * 0.9 <= st <= S0 * 1.1:
                strikes.append(st)
        
        # Mock volatility since NSE API doesn't provide historical vol
        sigma = 0.20 # Default 20% vol
        T = 30 / 365.0 # Basic 30 days proxy for simplicity
        
        payload = {
            "spot_price": S0,
            "risk_free_rate": 0.065,
            "time_to_maturity": T,
            "historical_volatility": sigma,
            "strikes": strikes
        }
        
        redis.xadd("stream:options.raw_fetched", {
            "symbol": symbol, 
            "data": json.dumps(payload)
        })
        logger.info(f"Published raw options chain for {symbol} with {len(strikes)} strikes.")
    except Exception as e:
        logger.error(f"Error fetching/publishing options for {symbol}: {e}")

@shared_task(queue='ingestion', name='ingestion.fetch_and_publish_options')
def fetch_and_publish_options(symbol: str = "NIFTY"):
    """
    Pulls raw chain from NSE wrapper and drops it into Redis Streams
    """
    asyncio.run(_fetch_and_publish_options_async(symbol))
