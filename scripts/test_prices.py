
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import MarketPriceFetcher

async def test_prices():
    fetcher = MarketPriceFetcher()
    symbols = ["NIFTY", "BANKNIFTY", "RELIANCE.NS", "INFY.NS", "HDFCBANK.NS", "TCS.NS", "ICICIBANK.NS"]
    
    print("Fetching prices...")
    for sym in symbols:
        data = await fetcher.fetch(sym)
        if data:
            print(f"[{sym}] Price: {data.get('last_price')} (Volume: {data.get('volume')})")
        else:
            print(f"[{sym}] FAILED")

if __name__ == "__main__":
    asyncio.run(test_prices())
