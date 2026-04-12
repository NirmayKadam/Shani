import asyncio
import logging
import sys
import os

# Add the project root to sys.path so 'app' can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.NewsSentiment.Ingestion.NewsIngestor import NewsIngestor

async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    
    Ingestor = NewsIngestor()
    print("\n[+] Initialising NewsIngestor...")
    await Ingestor.Initialise()
    
    Symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "INFY", "HDFCBANK", "TCS", "ICICIBANK"]
    
    try:
        for Symbol in Symbols:
            print(f"\n[+] Triggering ingestion for: {Symbol}")
            try:
                Articles = await Ingestor.IngestForSymbol(Symbol)
                print(f"\n======================================")
                print(f"Results for {Symbol}")
                print(f"======================================")
                print(f"Total new articles fetched & dispatched: {len(Articles)}\n")
                
                for i, Article in enumerate(Articles, 1):
                    print(f"{i}. {Article.Headline}")
            except Exception as e:
                print(f"\n[!] Error during ingestion for {Symbol}: {e}")
                
        print("\n[+] Done pushing articles to worker queue.")
    finally:
        print("\n[+] Shutting down Ingestor...")
        await Ingestor.Shutdown()

if __name__ == "__main__":
    asyncio.run(main())
