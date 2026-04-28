
import asyncio
import json
from domains.analytics.api.analysis_service import AnalysisService

async def test_service():
    symbol = "NIFTY"
    service = AnalysisService()
    print(f"--- Calling AnalysisService.analyze('{symbol}') ---")
    try:
        response = await service.analyze(symbol)
        print("Response Model:")
        print(f"  Symbol: {response.symbol}")
        print(f"  Sentiment: {response.sentiment}")
        print(f"  Technical Forecast: {response.technical_forecast}")
        print(f"  Status: {response.status}")
        
        # Test individual components
        md = await service._read_market_data(symbol)
        hl = await service._read_headlines(symbol)
        se = await service._read_sentiment(symbol)
        tf = await service._read_technical_forecast(symbol)
        
        print("\nInternal reads:")
        print(f"  _read_market_data: {md is not None}")
        print(f"  _read_headlines: {len(hl)}")
        print(f"  _read_sentiment: {se is not None}")
        print(f"  _read_technical_forecast: {tf is not None}")
        
    except Exception as e:
        print(f"Service call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_service())
