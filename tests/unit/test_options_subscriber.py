import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import AsyncMock
import pytest

from domains.analytics.infrastructure.options_subscriber import OptionsPricingSubscriber
from shared.constants import Streams, Channels


def _published_event(mock_redis) -> dict:
    """The priced event as written to the stream by DurableEventStream.publish."""
    stream, fields = mock_redis.xadd.call_args[0][:2]
    assert stream == Streams.OPTIONS_PRICED
    assert mock_redis.xadd.call_args.kwargs.get("maxlen")  # streams are length-bounded
    return json.loads(fields["payload"])


@pytest.mark.unit
async def test_options_pricing_subscriber_process_event():
    mock_redis = AsyncMock()
    with ThreadPoolExecutor(max_workers=2) as executor:
        subscriber = OptionsPricingSubscriber(mock_redis, executor=executor)
        await subscriber.process_event({
            "symbol": "RELIANCE",
            "data": {
                "spot_price": 2500.0,
                "risk_free_rate": 0.065,
                "dividend_yield": 0.012,
                "time_to_maturity": 0.08,  # ~30 days
                "strikes_data": [
                    {"strike": 2500.0, "type": "CE", "iv": 0.18, "ltp": 45.0},
                    {"strike": 2500.0, "type": "PE", "iv": 0.19, "ltp": 42.0}
                ]
            },
        })

    # Check that it set cache in Redis
    mock_redis.set.assert_called_once()
    cache_key = mock_redis.set.call_args[0][0]
    assert "market:options:priced:RELIANCE" in cache_key

    cache_value = json.loads(mock_redis.set.call_args[0][1])
    assert cache_value["symbol"] == "RELIANCE"
    assert len(cache_value["chain"]) == 1

    priced_strike = cache_value["chain"][0]
    assert priced_strike["strike"] == 2500.0
    assert priced_strike["fair_call"] is not None
    assert priced_strike["fair_put"] is not None
    assert priced_strike["live_call"] == 45.0
    assert priced_strike["live_put"] == 42.0

    # Verify BSM call/put fair values are correct and realistic
    assert priced_strike["bs_fair_call"] == pytest.approx(56.16, abs=0.1)
    assert priced_strike["bs_fair_put"] == pytest.approx(48.31, abs=0.1)

    # Durable stream and live Pub/Sub both published
    assert _published_event(mock_redis)["symbol"] == "RELIANCE"
    mock_redis.publish.assert_called_once()
    assert Channels.OPTIONS_UPDATED.format(symbol="RELIANCE") in mock_redis.publish.call_args[0][0]


@pytest.mark.unit
async def test_priced_event_carries_alert_snapshot_and_skips_legs_without_iv():
    mock_redis = AsyncMock()
    with ThreadPoolExecutor(max_workers=2) as executor:
        subscriber = OptionsPricingSubscriber(mock_redis, executor=executor)
        await subscriber.process_event({
            "symbol": "NIFTY",
            "data": {
                "spot_price": 24000.0,
                "risk_free_rate": 0.065,
                "dividend_yield": 0.0,
                "time_to_maturity": 0.08,
                "expiry": "2026-06-25",
                "strikes_data": [
                    {"strike": 23900.0, "type": "CE", "iv": 0.16, "ltp": 300.0},
                    {"strike": 24050.0, "type": "CE", "iv": 0.14, "ltp": 200.0},
                    {"strike": 24050.0, "type": "PE", "iv": 0.0, "ltp": 210.0},  # no usable IV
                ],
            },
        })

    event = _published_event(mock_redis)
    assert event["spot_price"] == 24000.0
    assert event["expiry"] == "2026-06-25"
    assert event["last_updated"]
    # ATM = strike nearest spot (24050), its call IV in percent
    assert event["atm_iv_pct"] == pytest.approx(14.0)

    row = next(r for r in event["chain"] if r["strike"] == 24050.0)
    assert row["fair_call"] is not None and row["bs_fair_call"] is not None
    assert row["fair_put"] is None and row["bs_fair_put"] is None and row["put_iv"] is None


@pytest.mark.unit
def test_default_executor_is_a_spawn_process_pool_and_is_closed(monkeypatch):
    monkeypatch.setenv("PRICING_WORKERS", "1")
    subscriber = OptionsPricingSubscriber(AsyncMock())
    executor = subscriber._get_executor()
    try:
        assert isinstance(executor, ProcessPoolExecutor)
        assert executor._mp_context.get_start_method() == "spawn"
    finally:
        subscriber.close()
    assert subscriber._executor is None


@pytest.mark.unit
async def test_chain_is_split_into_one_batched_solve_per_worker():
    from unittest.mock import patch
    calls = []

    def fake_chunk(S0, T, r, q, strikes, sigmas, is_call):
        calls.append(len(strikes))
        return [1.0] * len(strikes)

    strikes_data = [{"strike": 24000.0 + 50 * k, "type": t, "iv": 0.15, "ltp": 100.0}
                    for k in range(-25, 25) for t in ("CE", "PE")]
    with ThreadPoolExecutor(max_workers=4) as executor, \
         patch("domains.analytics.infrastructure.options_subscriber._price_chunk_sync", side_effect=fake_chunk):
        subscriber = OptionsPricingSubscriber(AsyncMock(), executor=executor)
        await subscriber.process_event({"symbol": "NIFTY", "data": {
            "spot_price": 24000.0, "risk_free_rate": 0.065, "dividend_yield": 0.0,
            "time_to_maturity": 0.05, "strikes_data": strikes_data}})

    assert sorted(calls) == [25, 25, 25, 25]  # 100 contracts -> 4 chunks of one batched solve each
