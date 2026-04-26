import asyncio
import logging
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import OptionChainFetcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def main():
    fetcher = OptionChainFetcher()
    try:
        for symbol in ["NIFTY", "RELIANCE"]:
            print(f"Fetching {symbol}...")
            data = await fetcher.fetch(symbol)
            if data:
                print(f"[OK] {symbol} Success!")
                print(f"   Summary: {data.get('summary')}")
            else:
                print(f"[FAIL] {symbol} Failed")
    finally:
        await fetcher.close()

if __name__ == "__main__":
    asyncio.run(main())
