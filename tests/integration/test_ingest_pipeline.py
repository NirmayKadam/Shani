import asyncio
import logging
from domains.ingestion.application.tasks.ingestion_tasks import get_service

async def test_news_ingestion_pipeline():
    """
    Automated test for triggering news ingestion.
    """
    svc = get_service()
    Symbols = ["NIFTY", "RELIANCE"]
    
    print("\n[+] Triggering news ingestion...")
    for Symbol in Symbols:
        try:
            await svc.ingest_news(Symbol)
            print(f"  ✅ Ingestion dispatched for {Symbol}")
        except Exception as e:
            assert False, f"Failed ingestion for {Symbol}: {e}"

if __name__ == "__main__":
    asyncio.run(test_news_ingestion_pipeline())
