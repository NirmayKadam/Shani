"""
Shared test fixtures for the MarketSentimentAnalysis2 test suite.

Provides mock objects and sample data to enable offline unit testing
without requiring Redis, Postgres, or live market API access.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Sample Data Fixtures ────────────────────────────────────────

@pytest.fixture
def sample_option_chain_raw():
    """Raw NSE-format option chain data for parsing tests."""
    return {
        "records": {
            "underlyingValue": 24500.0,
            "expiryDates": ["29-May-2026", "05-Jun-2026"],
            "data": [
                {
                    "strikePrice": 24400,
                    "expiryDate": "29-May-2026",
                    "CE": {
                        "lastPrice": 150.0,
                        "openInterest": 50000,
                        "totalTradedVolume": 12000,
                        "impliedVolatility": 14.5,
                    },
                    "PE": {
                        "lastPrice": 80.0,
                        "openInterest": 45000,
                        "totalTradedVolume": 10000,
                        "impliedVolatility": 15.2,
                    },
                },
                {
                    "strikePrice": 24500,
                    "expiryDate": "29-May-2026",
                    "CE": {
                        "lastPrice": 100.0,
                        "openInterest": 80000,
                        "totalTradedVolume": 20000,
                        "impliedVolatility": 13.8,
                    },
                    "PE": {
                        "lastPrice": 110.0,
                        "openInterest": 75000,
                        "totalTradedVolume": 18000,
                        "impliedVolatility": 14.0,
                    },
                },
                {
                    "strikePrice": 24600,
                    "expiryDate": "29-May-2026",
                    "CE": {
                        "lastPrice": 60.0,
                        "openInterest": 40000,
                        "totalTradedVolume": 8000,
                        "impliedVolatility": 15.5,
                    },
                    "PE": {
                        "lastPrice": 170.0,
                        "openInterest": 35000,
                        "totalTradedVolume": 7000,
                        "impliedVolatility": 16.0,
                    },
                },
            ],
        }
    }


@pytest.fixture
def sample_parsed_chain():
    """Parsed option chain data (post-processing format)."""
    return {
        "symbol": "NIFTY",
        "spot_price": 24500.0,
        "expiry_dates": ["29-May-2026", "05-Jun-2026"],
        "chains": {
            "2026-05-29": [
                {"strike": 24400.0, "type": "CE", "last_price": 150.0, "oi": 50000, "volume": 12000, "iv": 14.5, "expiry": "2026-05-29"},
                {"strike": 24400.0, "type": "PE", "last_price": 80.0, "oi": 45000, "volume": 10000, "iv": 15.2, "expiry": "2026-05-29"},
                {"strike": 24500.0, "type": "CE", "last_price": 100.0, "oi": 80000, "volume": 20000, "iv": 13.8, "expiry": "2026-05-29"},
                {"strike": 24500.0, "type": "PE", "last_price": 110.0, "oi": 75000, "volume": 18000, "iv": 14.0, "expiry": "2026-05-29"},
                {"strike": 24600.0, "type": "CE", "last_price": 60.0, "oi": 40000, "volume": 8000, "iv": 15.5, "expiry": "2026-05-29"},
                {"strike": 24600.0, "type": "PE", "last_price": 170.0, "oi": 35000, "volume": 7000, "iv": 16.0, "expiry": "2026-05-29"},
            ]
        },
    }


# ── Mock Fixtures ───────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """AsyncMock Redis client for unit tests."""
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.exists.return_value = False
    redis.zadd.return_value = 1
    redis.xadd.return_value = b"1234567890-0"
    redis.publish.return_value = 1
    return redis


@pytest.fixture
def mock_publisher():
    """AsyncMock for IEventPublisherPort."""
    publisher = AsyncMock()
    publisher.publish.return_value = None
    return publisher


@pytest.fixture(autouse=True)
def clear_validator_cache():
    """Automatically clear both SymbolValidator caches between tests."""
    from shared.utils.symbol_validator import SymbolValidator
    SymbolValidator.validate.cache_clear()
    SymbolValidator.get_clean_symbol.cache_clear()
    yield
    SymbolValidator.validate.cache_clear()
    SymbolValidator.get_clean_symbol.cache_clear()


@pytest.fixture
def test_client():
    """TestClient for FastAPI endpoint tests, with the app's startup network calls mocked.

    The real lifespan pings Redis and warms an NSE session (tens of seconds offline); endpoint
    tests patch the clients they need themselves.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    with patch("shared.infrastructure.redis_client.get_redis_client", new=AsyncMock()), \
         patch("shared.infrastructure.redis_client.close_redis_client", new=AsyncMock()), \
         patch("shared.infrastructure.database.close_database_pool", new=AsyncMock()), \
         patch("domains.ingestion.api.nse_options_router_api.startup_nse_client", new=AsyncMock()), \
         patch("domains.ingestion.api.nse_options_router_api.shutdown_nse_client", new=AsyncMock()), \
         patch("domains.analytics.api.pricer_router_api._historical_volatility_sync", return_value=12.5):
        with TestClient(app) as client:
            yield client
