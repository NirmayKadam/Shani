import asyncio
import logging
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.ingestion.infrastructure.adapters.outbound.nse_api_adapter import OptionChainFetcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def main():
    fetcher = OptionChainFetcher()
    try:
        print("Fetching NIFTY...")
        data = await fetcher.fetch("NIFTY")
        if data:
            print("[OK] NIFTY Success!")
            print(f"   Summary: {data.get('summary')}")
        else:
            print("[FAIL] NIFTY Failed")
    finally:
        await fetcher.close()

if __name__ == "__main__":
    asyncio.run(main())
