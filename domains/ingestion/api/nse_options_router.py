"""
File Overview: Inbound wrapper API for fetching live NSE option chains. 
Used by background ingestion workers to bypass WAF.

All Functions/Classes:
- nse_options_router: FastAPI router for NSE proxy.
- refresh_nse_cookies: Session manager. Take NSE homepage and send updated cookie jar.
- get_option_chain: Live fetcher. Take symbol/index-flag and send raw NSE records.

Endpoints/APIs: GET /options/{symbol}

Database Tables: None (Direct NSE API proxy)
"""
from fastapi import APIRouter, HTTPException
import httpx
from typing import Dict, Any
from urllib.parse import quote

nse_options_router = APIRouter()

# Constants for NSE API
NSE_BASE_URL = "https://www.nseindia.com"
INDICES_API_URL = "https://www.nseindia.com/api/option-chain-indices?symbol="
EQUITIES_API_URL = "https://www.nseindia.com/api/option-chain-equities?symbol="

# Standard browser headers to prevent getting blocked
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

# Global client to maintain connection pools and cookies across requests
client = httpx.AsyncClient(headers=HEADERS, timeout=10.0)

async def refresh_nse_cookies():
    """Hits the NSE homepage purely to generate fresh session cookies."""
    try:
        response = await client.get(NSE_BASE_URL)
        response.raise_for_status()
        print("NSE Cookies refreshed successfully.")
    except Exception as e:
        print(f"Failed to fetch cookies: {e}")

@nse_options_router.on_event("startup")
async def startup_event():
    # Initialize cookies when the FastAPI server starts
    await refresh_nse_cookies()

@nse_options_router.get("/options/{symbol}", response_model=Dict[str, Any])
async def get_option_chain(symbol: str, is_index: bool = True):
    """
    Fetches the live option chain for a given symbol from NSE.
    """
    safe_symbol = quote(symbol.upper())
    
    url = INDICES_API_URL + safe_symbol if is_index else EQUITIES_API_URL + safe_symbol
    
    try:
        response = await client.get(url)
        
        # If we get unauthorized, our cookies likely expired. Refresh and retry.
        if response.status_code in [401, 403]:
            print("🔄 Cookies expired. Refreshing...")
            await refresh_nse_cookies()
            response = await client.get(url)
            
        response.raise_for_status()
        data = response.json()
        
        if 'records' not in data:
            raise HTTPException(status_code=404, detail="No reliable option records found")

        return {
            "symbol": symbol.upper(),
            "timestamp": data['records']['timestamp'],
            "underlying_value": data['records']['underlyingValue'],
            "raw_chain": data['records']['data'] 
        }
        
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"NSE API Error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Fetch Error: {str(e)}")
