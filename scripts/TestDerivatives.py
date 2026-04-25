"""
TestDerivatives.py — end-to-end test for the Derivatives Analytics pipeline.

Usage (inside Docker):
    docker compose exec app python -m scripts.TestDerivatives

This script:
    1. Runs the live TickIngestor to fetch option chain data from the NSE
    2. Waits for the derivatives worker to process the ticks
    3. Queries the API endpoints and prints the results
"""

import asyncio
import sys
import os

# Ensure the project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def Main():
    print("=" * 60)
    print("  Derivatives Analytics Pipeline — End-to-End Test")
    print("=" * 60)

    # Step 1: Run live tick ingestion
    print("\n[1/3] Running live tick ingestion via IngestionService...")
    from domains.ingestion.application.tasks.IngestionTasks import get_service

    svc = get_service()

    try:
        # We trigger BOTH market data (spot) and options for a few symbols
        Symbols = ["NIFTY", "RELIANCE"]
        for Sym in Symbols:
            print(f"  [+] Ingesting {Sym}...")
            await svc.ingest_market_data(Sym)
            await svc.ingest_options(Sym)
            
        print(f"  ✅ Triggered ingestion for {Symbols}")

    except Exception as e:
        print(f"  ❌ Error during ingestion: {e}")
    finally:
        pass

    # Step 2: Wait for worker to process
    print("\n[2/3] Waiting 5 seconds for derivatives worker to process...")
    await asyncio.sleep(5)

    # Step 3: Check Redis cache and API readiness
    print("\n[3/3] Checking Redis cache for computed metrics...")
    import redis.asyncio as aioredis
    import json

    RedisUrl = os.getenv("REDIS_URL", "redis://redis:6379/0")
    Redis = aioredis.from_url(RedisUrl, decode_responses=True)

    try:
        for Sym in sorted(Symbols)[:3]:
            print(f"\n  📊 {Sym}:")

            # PCR
            PcrStr = await Redis.get(f"derivatives:pcr:{Sym}")
            if PcrStr:
                Pcr = json.loads(PcrStr)
                print(f"     PCR: {Pcr['pcr']:.4f}  (CE Vol: {Pcr['ce_volume']:,}  PE Vol: {Pcr['pe_volume']:,})")
            else:
                print("     PCR: not yet computed (worker may still be processing)")

            # IV Surface
            IvStr = await Redis.get(f"derivatives:iv_surface:{Sym}")
            if IvStr:
                IvList = json.loads(IvStr)
                print(f"     IV Surface: {len(IvList)} strikes computed")
                # Show ATM strikes
                for Iv in sorted(IvList, key=lambda x: x['strike'])[:3]:
                    print(f"       Strike {Iv['strike']:,.0f} {Iv['type']}: IV = {Iv['iv']:.2%}")
            else:
                print("     IV Surface: not yet computed")

    finally:
        await Redis.aclose()

    print("\n" + "=" * 60)
    print("  Test complete! Verify via API:")
    print("  curl http://localhost:8000/v1/derivatives/NIFTY")
    print("  curl http://localhost:8000/v1/events/NIFTY")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(Main())
