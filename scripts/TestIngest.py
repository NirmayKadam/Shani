import asyncio
import logging
import sys
import os

# Add the project root to sys.path so 'app' can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domains.ingestion.application.tasks.IngestionTasks import get_service

async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    
    svc = get_service()
    print("\n[+] Initialising IngestionService...")
    
    Symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "INFY", "HDFCBANK", "TCS", "ICICIBANK"]
    
    try:
        for Symbol in Symbols:
            print(f"\n[+] Triggering news ingestion for: {Symbol}")
            try:
                await svc.ingest_news(Symbol)
                print(f"  ✅ Ingestion task dispatched to bus for {Symbol}")
            except Exception as e:
                print(f"\n[!] Error during ingestion for {Symbol}: {e}")
                
        print("\n[+] Done triggering news ingestion.")
    finally:
        # No shutdown needed for sync-redis based IngestionService
        pass

if __name__ == "__main__":
    asyncio.run(main())
