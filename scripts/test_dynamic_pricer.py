import asyncio
import os
import sys
import json

# Add project root to path
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

async def run_tests():
    print("Testing dynamic pricer retrieval...")
    
    # 1. Test F&O Stock (TCS)
    print("\n--- Testing TCS (F&O Stock) ---")
    response = client.get("/v1/pricer/ticker/TCS")
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Symbol: {data.get('symbol')}")
        print(f"Stock Price: {data.get('stock_price')}")
        print(f"Source: {data.get('source')}")
        print(f"Expiries Count: {len(data.get('expiry_dates', []))}")
        print(f"Option Chains Count: {len(data.get('option_chains', {}))}")
    else:
        print(f"Error: {response.text}")
        
    # 2. Test Non-F&O Stock (ZOMATO)
    print("\n--- Testing ZOMATO (Non-F&O Stock) ---")
    response = client.get("/v1/pricer/ticker/ZOMATO")
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Symbol: {data.get('symbol')}")
        print(f"Stock Price: {data.get('stock_price')}")
        print(f"Source: {data.get('source')}")
        print(f"Expiries: {data.get('expiry_dates')}")
        print(f"Option Chains: {data.get('option_chains')}")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    asyncio.run(run_tests())
