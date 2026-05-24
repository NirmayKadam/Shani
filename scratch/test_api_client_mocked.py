import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

# Ensure root directory is in sys.path
sys.path.append(os.getcwd())

# Define mock Redis data
MOCK_SPOT = 2500.0
MOCK_EXPIRIES = ["2026-06-25", "2026-07-30"]

MOCK_RAW_OPTIONS = {
    "symbol": "RELIANCE",
    "spot_price": MOCK_SPOT,
    "expiry_dates": MOCK_EXPIRIES,
    "chains": {
        "2026-06-25": [
            {"strike": 2400.0, "type": "CE", "last_price": 120.0, "oi": 5000, "volume": 12000, "iv": 0.18, "expiry": "2026-06-25"},
            {"strike": 2400.0, "type": "PE", "last_price": 15.0, "oi": 3000, "volume": 8000, "iv": 0.19, "expiry": "2026-06-25"},
            {"strike": 2500.0, "type": "CE", "last_price": 45.0, "oi": 15000, "volume": 35000, "iv": 0.18, "expiry": "2026-06-25"},
            {"strike": 2500.0, "type": "PE", "last_price": 42.0, "oi": 14000, "volume": 32000, "iv": 0.19, "expiry": "2026-06-25"},
            {"strike": 2600.0, "type": "CE", "last_price": 10.0, "oi": 6000, "volume": 15000, "iv": 0.18, "expiry": "2026-06-25"},
            {"strike": 2600.0, "type": "PE", "last_price": 110.0, "oi": 2000, "volume": 5000, "iv": 0.19, "expiry": "2026-06-25"},
        ]
    },
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "summary": {"total_strikes": 6}
}

MOCK_PRICED_OPTIONS = {
    "symbol": "RELIANCE",
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "chain": [
        {
            "strike": 2400.0,
            "fair_call": 121.50,
            "fair_put": 14.80,
            "call_iv": 0.18,
            "put_iv": 0.19,
            "bs_fair_call": 120.90,
            "bs_fair_put": 14.20,
            "live_call": 120.0,
            "live_put": 15.0
        },
        {
            "strike": 2500.0,
            "fair_call": 46.20,
            "fair_put": 41.80,
            "call_iv": 0.18,
            "put_iv": 0.19,
            "bs_fair_call": 45.80,
            "bs_fair_put": 41.20,
            "live_call": 45.0,
            "live_put": 42.0
        },
        {
            "strike": 2600.0,
            "fair_call": 9.80,
            "fair_put": 109.50,
            "call_iv": 0.18,
            "put_iv": 0.19,
            "bs_fair_call": 9.50,
            "bs_fair_put": 108.90,
            "live_call": 10.0,
            "live_put": 110.0
        }
    ]
}

MOCK_SENTIMENT_SIGNAL = {
    "symbol": "RELIANCE",
    "composite_label": "BULLISH",
    "strength": 0.76,
    "sentiment_avg": 0.42,
    "prediction": "VOL_CRUSH",
    "composed_at": datetime.now(timezone.utc).isoformat(),
    "metadata": {
        "daily_count": 18,
        "pred_confidence": 0.85
    }
}

async def get_mock_redis():
    mock = AsyncMock()
    
    async def mock_get(key):
        if "market:options:priced:" in key:
            return json.dumps(MOCK_PRICED_OPTIONS)
        elif "market:options:" in key:
            return json.dumps(MOCK_RAW_OPTIONS)
        elif "sentiment:signal:" in key:
            return json.dumps(MOCK_SENTIMENT_SIGNAL)
        return None

    mock.get = mock_get
    mock.ping = AsyncMock(return_value=True)
    return mock

# Patch redis client getter
@patch("shared.infrastructure.redis_client.get_redis_client", get_mock_redis)
def test_all():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    
    print("=== [1] GET / (Health Check) ===")
    res = client.get("/")
    print(f"Status: {res.status_code}")
    print(json.dumps(res.json(), indent=2))
    
    print("\n=== [2] GET /v1/symbols ===")
    res = client.get("/v1/symbols")
    print(f"Status: {res.status_code}")
    print(json.dumps(res.json(), indent=2))
    
    print("\n=== [3] GET /v1/signals/RELIANCE ===")
    res = client.get("/v1/signals/RELIANCE")
    print(f"Status: {res.status_code}")
    print(json.dumps(res.json(), indent=2))
    
    print("\n=== [4] GET /v1/derivatives/RELIANCE ===")
    res = client.get("/v1/derivatives/RELIANCE")
    print(f"Status: {res.status_code}")
    print(json.dumps(res.json(), indent=2))

    print("\n=== [5] GET /v1/predictions/RELIANCE ===")
    res = client.get("/v1/predictions/RELIANCE")
    print(f"Status: {res.status_code}")
    print(json.dumps(res.json(), indent=2))

if __name__ == "__main__":
    test_all()
