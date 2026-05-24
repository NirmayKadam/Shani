import requests
import json

BASE_URL = "http://localhost:8000/v1/pricer"

def test_ticker_endpoint():
    print("Testing GET /pricer/ticker/AAPL...")
    try:
        r = requests.get(f"{BASE_URL}/ticker/AAPL")
        print(f"Status Code: {r.status_code}")
        print("Response JSON:")
        print(json.dumps(r.json(), indent=2))
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "AAPL"
        assert data["stock_price"] == 182.45
        print("  [SUCCESS] AAPL Ticker Mock endpoint works perfectly!")
    except Exception as e:
        print(f"  [ERROR] GET /ticker/AAPL failed: {e}")

def test_calculate_endpoint():
    print("\nTesting POST /pricer/calculate (Call option pricing)...")
    payload = {
        "S0": 182.45,
        "K": 185.00,
        "T_days": 60,
        "r": 5.25,
        "sigma": 28.4,
        "option_type": "call",
        "q": 0.55,
        "market_mid": 7.10
    }
    try:
        r = requests.post(f"{BASE_URL}/calculate", json=payload)
        print(f"Status Code: {r.status_code}")
        print("Response JSON:")
        print(json.dumps(r.json(), indent=2))
        assert r.status_code == 200
        data = r.json()
        
        # Verify values approximate spec
        print(f"Intermediate d1: {data['d1']}")
        print(f"Intermediate d2: {data['d2']}")
        print(f"Cumulative N(d1): {data['Nd1']}")
        print(f"Cumulative N(d2): {data['Nd2']}")
        print(f"BSM Fair Value: ${data['fair_value']}")
        print(f"Calculated Edge: ${data['edge']}")
        
        assert abs(data["fair_value"] - 7.84) < 0.05, f"Expected BSM Fair Value near 7.84, got {data['fair_value']}"
        assert abs(data["edge"] - 0.74) < 0.05, f"Expected Edge near 0.74, got {data['edge']}"
        print("  [SUCCESS] POST /calculate BSM Option pricing works perfectly!")
    except Exception as e:
        print(f"  [ERROR] POST /calculate failed: {e}")

if __name__ == "__main__":
    test_ticker_endpoint()
    test_calculate_endpoint()
