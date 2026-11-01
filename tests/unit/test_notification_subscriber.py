from unittest.mock import AsyncMock
import pytest

from domains.notifications.domain.value_objects import DeliveryChannel
from domains.notifications.infrastructure.subscribers.notification_subscriber import NotificationStreamSubscriber


@pytest.mark.asyncio
async def test_notification_subscriber_evaluates_once_per_priced_chain():
    mock_repo = AsyncMock()
    mock_repo.get_active_rules_by_symbol.return_value = []
    subscriber = NotificationStreamSubscriber(redis_client=AsyncMock(), repository=mock_repo)
    subscriber.evaluator = AsyncMock()

    chain = [{"strike": 24000.0 + 50 * i, "live_call": 100.0, "call_iv": 0.15} for i in range(40)]
    await subscriber.process_event({"symbol": "NIFTY", "spot_price": 24200.0, "atm_iv_pct": 15.2, "chain": chain})

    # One evaluation for the whole chain, against the symbol-level snapshot (no per-strike loop).
    subscriber.evaluator.evaluate_tick_event.assert_awaited_once_with(
        "NIFTY", {"spot_price": 24200.0, "atm_iv_pct": 15.2}
    )


@pytest.mark.asyncio
async def test_notification_subscriber_ignores_events_without_symbol():
    subscriber = NotificationStreamSubscriber(redis_client=AsyncMock(), repository=AsyncMock())
    subscriber.evaluator = AsyncMock()

    await subscriber.process_event({"spot_price": 1.0})

    subscriber.evaluator.evaluate_tick_event.assert_not_awaited()


def test_websocket_channel_is_wired_to_redis():
    redis = AsyncMock()
    subscriber = NotificationStreamSubscriber(redis_client=redis, repository=AsyncMock())
    ws_channel = subscriber.channels[DeliveryChannel.WEBSOCKET]
    # Previously EventBus() was built without a Redis client and raised TypeError on dispatch.
    assert ws_channel._event_bus is not None
    assert ws_channel._event_bus._Redis is redis
