import asyncio
import os
import json
import redis.asyncio as aioredis
from domains.ingestion.application.tasks.ingestion_tasks import get_service

async def test_derivatives_pipeline_e2e():
    """
    Automated end-to-end test for the Derivatives Analytics pipeline.
    """
    print("\n[1/3] Triggering ingestion...")
    svc = get_service()
    Symbols = ["NIFTY", "RELIANCE"]
    
    for Sym in Symbols:
        await svc.ingest_market_data(Sym)
        await svc.ingest_options(Sym)
    
    print(f"\n[2/3] Waiting for processing...")
    await asyncio.sleep(5)
    
    print("\n[3/3] Verifying Redis results...")
    RedisUrl = os.getenv("REDIS_URL", "redis://redis:6379/0")
    Redis = aioredis.from_url(RedisUrl, decode_responses=True)
    
    try:
        for Sym in Symbols:
            PcrStr = await Redis.get(f"derivatives:pcr:{Sym}")
            assert PcrStr is not None, f"PCR state missing for {Sym}"
            
            Pcr = json.loads(PcrStr)
            assert "pcr" in Pcr, "Invalid PCR format"
            print(f"  ✅ {Sym} PCR: {Pcr['pcr']:.4f}")

            IvStr = await Redis.get(f"derivatives:iv_surface:{Sym}")
            assert IvStr is not None, f"IV Surface state missing for {Sym}"
            
            IvList = json.loads(IvStr)
            assert len(IvList) > 0, "Empty IV surface"
            print(f"  ✅ {Sym} IV Surface: {len(IvList)} points")
            
    finally:
        await Redis.aclose()

if __name__ == "__main__":
    asyncio.run(test_derivatives_pipeline_e2e())
