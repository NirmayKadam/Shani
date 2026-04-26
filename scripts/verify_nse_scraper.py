import asyncio
import logging
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import OptionChainFetcher, MarketPriceFetcher

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def test_nse_scraper(symbol: str):
    print(f"\n--- Testing OptionChainFetcher for {symbol} ---")
    fetcher = OptionChainFetcher()
    
    try:
        print(f"Fetching options for: {symbol}")
        data = await fetcher.fetch(symbol)
        
        if data:
            print(f"[OK] Success! Fetched {symbol} data")
            print(f"   Spot Price: {data.get('spot_price')}")
            print(f"   Expiries: {', '.join(data.get('expiry_dates', [])[:3])} ...")
        else:
            print(f"[FAIL] Failed to fetch data for {symbol}")
            
    except Exception as e:
        print(f"[ERROR] Error during fetch: {e}")
    finally:
        await fetcher.close()

async def test_market_price_fetcher(symbol: str):
    print(f"\n--- Testing MarketPriceFetcher for {symbol} ---")
    fetcher = MarketPriceFetcher()
    
    try:
        print(f"Fetching market price for: {symbol}")
        data = await fetcher.fetch(symbol)
        
        if data:
            print(f"[OK] Success! Fetched {symbol} market price")
            print(f"   Last Price: {data.get('last_price')}")
            print(f"   Market Status: {data.get('market_status')}")
        else:
            print(f"[FAIL] Failed to fetch market price for {symbol}")
            
    except Exception as e:
        print(f"[ERROR] Error during fetch: {e}")

async def main():
    for symbol in ["NIFTY", "RELIANCE"]:
        await test_market_price_fetcher(symbol)
        await test_nse_scraper(symbol)

if __name__ == "__main__":
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())
