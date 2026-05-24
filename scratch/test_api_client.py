import json
import os
import sys
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.append(os.getcwd())

from app.main import app

def check_endpoints():
    client = TestClient(app)
    
    print("=== [1] GET / (Health Check) ===")
    try:
        res = client.get("/")
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.json()}")
    except Exception as e:
        print(f"Failed: {e}")
        
    print("\n=== [2] GET /v1/symbols ===")
    try:
        res = client.get("/v1/symbols")
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.json()}")
    except Exception as e:
        print(f"Failed: {e}")

    test_symbols = ["RELIANCE", "NIFTY"]
    for sym in test_symbols:
        print(f"\n=== [3] GET /v1/signals/{sym} ===")
        try:
            res = client.get(f"/v1/signals/{sym}")
            print(f"Status Code: {res.status_code}")
            # Format nicely
            print(json.dumps(res.json(), indent=2))
        except Exception as e:
            print(f"Failed: {e}")
            
        print(f"\n=== [4] GET /v1/derivatives/{sym} ===")
        try:
            res = client.get(f"/v1/derivatives/{sym}")
            print(f"Status Code: {res.status_code}")
            # Print structure summary
            data = res.json()
            if "fair_priced_chain" in data:
                chain_len = len(data["fair_priced_chain"])
                print(f"PCR: {data.get('pcr')}, Total Strikes: {data.get('total_strikes')}, Priced Strikes Count: {chain_len}")
                if chain_len > 0:
                    print("Sample Priced Strike:")
                    print(json.dumps(data["fair_priced_chain"][0], indent=2))
            else:
                print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Failed: {e}")

        print(f"\n=== [5] GET /v1/predictions/{sym} ===")
        try:
            res = client.get(f"/v1/predictions/{sym}")
            print(f"Status Code: {res.status_code}")
            print(json.dumps(res.json(), indent=2))
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    check_endpoints()
