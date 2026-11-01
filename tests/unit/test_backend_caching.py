"""Phase 5 backend efficiency: poll leader, single-flight fetch, history cache, unchanged-chain skip."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class FakeRedis:
    """Just enough of redis.asyncio for SET NX/GET/EXISTS/DELETE (no expiry)."""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def exists(self, key):
        return int(key in self.store)

    async def delete(self, key):
        return int(self.store.pop(key, None) is not None)


@pytest.mark.unit
async def test_only_one_worker_claims_a_poll_slot():
    from domains.analytics.api.events_router_api import _claim_poll_slot
    redis = FakeRedis()
    with patch("shared.infrastructure.redis_client.get_redis_client", AsyncMock(return_value=redis)):
        claims = [await _claim_poll_slot("options", "NIFTY", 15) for _ in range(3)]
        other_symbol = await _claim_poll_slot("options", "BANKNIFTY", 15)
    assert claims == [True, False, False]
    assert other_symbol is True


@pytest.mark.unit
async def test_poll_slot_fails_open_without_redis():
    from domains.analytics.api.events_router_api import _claim_poll_slot
    with patch("shared.infrastructure.redis_client.get_redis_client", AsyncMock(side_effect=ConnectionError)):
        assert await _claim_poll_slot("price", "NIFTY", 5) is True


@pytest.mark.unit
async def test_concurrent_cache_misses_share_one_live_fetch():
    from domains.analytics.api import pricer_router_api as api
    from shared.constants import RedisKeys

    redis = FakeRedis()
    calls = []

    async def fake_live_fetch(symbol_clean, _redis):
        calls.append(symbol_clean)
        await asyncio.sleep(0.3)
        chain = {"symbol": symbol_clean, "spot_price": 100.0}
        await _redis.set(RedisKeys.MARKET_OPTIONS.format(symbol=symbol_clean), json.dumps(chain))
        return chain, None

    async def request():
        cached = await api._wait_for_concurrent_fetch(redis, "TCS.NS")
        if cached is not None:
            return "waited", cached
        return "fetched", (await api._single_flight_live_fetch("TCS.NS", redis))[0]

    with patch.object(api, "_live_fetch", side_effect=fake_live_fetch):
        first = asyncio.create_task(request())
        await asyncio.sleep(0.05)  # the first request holds the lock
        second = await request()
        first = await first

    assert calls == ["TCS.NS"]
    assert first[0] == "fetched" and second[0] == "waited"
    assert second[1]["spot_price"] == 100.0
    assert await redis.exists(api._fetch_lock_key("TCS.NS")) == 0  # lock released


@pytest.mark.unit
async def test_wait_returns_immediately_when_nobody_is_fetching():
    from domains.analytics.api import pricer_router_api as api
    assert await api._wait_for_concurrent_fetch(FakeRedis(), "TCS.NS") is None
    # An AsyncMock client (truthy MagicMock results) must not be read as "lock held"
    assert await api._wait_for_concurrent_fetch(AsyncMock(), "TCS.NS") is None


@pytest.mark.unit
async def test_daily_history_is_fetched_once_then_served_from_redis():
    import pandas as pd
    from domains.analytics.api import derivatives_router_api as api

    redis = FakeRedis()
    hist = pd.DataFrame({"Close": [10.0, 11.0], "High": [10.5, 11.5], "Low": [9.5, 10.5]})
    ticker = MagicMock()
    ticker.history.return_value = hist
    with patch.object(api, "get_redis_client", AsyncMock(return_value=redis)), \
         patch("yfinance.Ticker", return_value=ticker):
        first = await api._daily_history("TCS.NS")
        second = await api._daily_history("TCS.NS")

    assert first == second == ([10.0, 11.0], [10.5, 11.5], [9.5, 10.5])
    assert ticker.history.call_count == 1


@pytest.mark.unit
async def test_failed_history_fetch_is_not_cached():
    from domains.analytics.api import derivatives_router_api as api

    redis = FakeRedis()
    with patch.object(api, "get_redis_client", AsyncMock(return_value=redis)), \
         patch("yfinance.Ticker", side_effect=RuntimeError("rate limited")):
        assert await api._daily_history("TCS.NS") == ([], None, None)
    assert redis.store == {}


def _dto(strike, opt_type, ltp, expiry="2099-12-30"):
    return SimpleNamespace(expiry=expiry, strike=strike, option_type=opt_type, ltp=ltp, iv=0.15,
                           oi=100, volume=10, underlying_price=24000.0, bid=None, bid_qty=None,
                           ask=None, ask_qty=None)


@pytest.mark.unit
def test_chain_digest_is_order_independent_and_sees_price_changes():
    from domains.ingestion.tasks.market_tasks import _chain_digest
    a, b = _dto(24000.0, "CE", 100.0), _dto(24000.0, "PE", 90.0)
    assert _chain_digest([a, b]) == _chain_digest([b, a])
    assert _chain_digest([a, b]) != _chain_digest([_dto(24000.0, "CE", 100.05), b])


@pytest.mark.unit
async def test_unchanged_chain_skips_persist_and_pricing():
    from domains.ingestion.tasks import market_tasks

    redis = FakeRedis()
    dtos = [_dto(24000.0, "CE", 100.0), _dto(24000.0, "PE", 90.0)]
    adapter = AsyncMock()
    adapter.fetch_option_chain.return_value = dtos
    adapter.fetch_price.return_value = {"dividend_yield": 0.0}

    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    publish = AsyncMock()

    with patch.object(market_tasks, "get_redis_client", AsyncMock(return_value=redis)), \
         patch("shared.infrastructure.database.get_database_pool", AsyncMock(return_value=pool)), \
         patch("domains.ingestion.infrastructure.outbound.adapter_factory.get_market_data_adapter",
               return_value=adapter), \
         patch.object(market_tasks.DurableEventStream, "publish", publish):
        await market_tasks._fetch_and_publish_options_async("NIFTY")
        await market_tasks._fetch_and_publish_options_async("NIFTY")  # same chain
        dtos[0].ltp = 101.0
        await market_tasks._fetch_and_publish_options_async("NIFTY")  # price moved

    assert conn.copy_records_to_table.await_count == 2
    assert publish.await_count == 2


def _jwt_with_exp(seconds_from_now):
    import base64
    import time
    body = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + seconds_from_now}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


@pytest.mark.unit
async def test_groww_token_is_shared_through_redis_until_expiry():
    from domains.ingestion.infrastructure.outbound import groww_api_adapter as mod

    redis = FakeRedis()
    token = _jwt_with_exp(3600)
    first = mod.GrowwApiAdapter(totp_secret="x", redis_client=redis)
    with patch.object(mod, "GROWW_SDK_AVAILABLE", True), \
         patch.object(mod.GrowwApiAdapter, "_fetch_token_sync", return_value=token) as fetch:
        assert await first._get_token() == token
        second = mod.GrowwApiAdapter(totp_secret="x", redis_client=redis)  # e.g. another worker
        assert await second._get_token() == token
    assert fetch.call_count == 1
    assert redis.store[mod._TOKEN_CACHE_KEY] == token


@pytest.mark.unit
async def test_expired_cached_groww_token_is_ignored():
    from domains.ingestion.infrastructure.outbound import groww_api_adapter as mod

    redis = FakeRedis()
    redis.store[mod._TOKEN_CACHE_KEY] = _jwt_with_exp(-10)
    adapter = mod.GrowwApiAdapter(redis_client=redis)
    assert await adapter._cached_token() is None


@pytest.mark.unit
async def test_groww_expiry_list_is_cached_for_the_day():
    from domains.ingestion.infrastructure.outbound import groww_api_adapter as mod

    adapter = mod.GrowwApiAdapter(redis_client=FakeRedis())
    adapter._fallback_adapter = AsyncMock()
    adapter._fallback_adapter.fetch_expiry_dates.return_value = ["2099-12-30"]
    assert await adapter._expiry_dates("NIFTY") == ["2099-12-30"]
    assert await adapter._expiry_dates("NIFTY") == ["2099-12-30"]
    assert adapter._fallback_adapter.fetch_expiry_dates.await_count == 1


@pytest.mark.unit
async def test_market_data_adapter_is_shared_per_event_loop():
    from domains.ingestion.infrastructure.outbound.adapter_factory import get_market_data_adapter
    assert get_market_data_adapter() is get_market_data_adapter()
