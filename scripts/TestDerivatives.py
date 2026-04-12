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

# Ensure the app module is importable
sys.path.insert(0, "/app")


async def Main():
    print("=" * 60)
    print("  Derivatives Analytics Pipeline — End-to-End Test")
    print("=" * 60)

    # Step 1: Run live tick ingestion
    print("\n[1/3] Running live tick ingestion...")
    from app.Derivatives.Ingestion.TickIngestor import TickIngestor

    Ingestor = TickIngestor()
    await Ingestor.Initialise()

    try:
        Ticks = await Ingestor.IngestOnce()
        print(f"  ✅ Fetched and persisted {len(Ticks)} live ticks from NSE")

        # Count tick types
        EqCount = sum(1 for t in Ticks if t.InstrumentType == "EQ")
        CeCount = sum(1 for t in Ticks if t.InstrumentType == "CE")
        PeCount = sum(1 for t in Ticks if t.InstrumentType == "PE")
        print(f"     EQ: {EqCount}  |  CE: {CeCount}  |  PE: {PeCount}")

        # Print a sample
        Symbols = set(t.Symbol for t in Ticks if t.InstrumentType == "EQ")
        for Sym in sorted(Symbols)[:3]:
            EqTick = next(t for t in Ticks if t.Symbol == Sym and t.InstrumentType == "EQ")
            print(f"     {Sym}: Spot = ₹{EqTick.LastPrice:,.2f}")

    finally:
        await Ingestor.Shutdown()

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
