import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import pytest

from domains.notifications.domain.entities import AlertRule, NotificationEvent
from domains.notifications.domain.value_objects import ConditionType, DeliveryChannel, AlertStatus
from domains.notifications.infrastructure.channels.websocket_channel import WebSocketNotificationChannelAdapter
from domains.notifications.infrastructure.channels.webhook_channel import WebhookNotificationChannelAdapter


@pytest.mark.asyncio
async def test_websocket_channel_dispatch():
    mock_bus = AsyncMock()
    mock_bus.publish.return_value = 1

    adapter = WebSocketNotificationChannelAdapter(event_bus=mock_bus)
    rule = AlertRule(
        id=uuid.uuid4(),
        symbol="NIFTY",
        condition_type=ConditionType.ABOVE_PRICE,
        threshold=24000.0,
        channels=[DeliveryChannel.WEBSOCKET],
    )
    event = NotificationEvent(
        id=uuid.uuid4(),
        rule_id=rule.id,
        symbol="NIFTY",
        condition_type=ConditionType.ABOVE_PRICE,
        triggered_value=24100.0,
        threshold=24000.0,
        message="NIFTY crossed 24000 threshold",
        channels=[DeliveryChannel.WEBSOCKET],
        timestamp=datetime.now(timezone.utc),
    )

    success = await adapter.dispatch(event, rule)
    assert success is True
    assert mock_bus.publish.called
    args = mock_bus.publish.call_args[0]
    assert "alerts.dispatched.NIFTY" in args[0]
    assert args[1]["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_webhook_channel_missing_url():
    adapter = WebhookNotificationChannelAdapter()
    rule = AlertRule(
        id=uuid.uuid4(),
        symbol="NIFTY",
        condition_type=ConditionType.ABOVE_PRICE,
        threshold=24000.0,
        channels=[DeliveryChannel.WEBHOOK],
        webhook_url=None,
    )
    event = NotificationEvent(
        id=uuid.uuid4(),
        rule_id=rule.id,
        symbol="NIFTY",
        condition_type=ConditionType.ABOVE_PRICE,
        triggered_value=24100.0,
        threshold=24000.0,
        message="NIFTY crossed threshold",
        channels=[DeliveryChannel.WEBHOOK],
    )

    success = await adapter.dispatch(event, rule)
    assert success is False


def _webhook_rule_and_event():
    rule = AlertRule(
        id=uuid.uuid4(), symbol="NIFTY", condition_type=ConditionType.ABOVE_PRICE, threshold=24000.0,
        channels=[DeliveryChannel.WEBHOOK], webhook_url="https://hooks.example.com/a", webhook_secret="s3cret",
    )
    event = NotificationEvent(
        id=uuid.uuid4(), rule_id=rule.id, symbol="NIFTY", condition_type=ConditionType.ABOVE_PRICE,
        triggered_value=24100.0, threshold=24000.0, message="NIFTY crossed", channels=[DeliveryChannel.WEBHOOK],
    )
    return rule, event


def _response(status):
    resp = AsyncMock()
    resp.status_code = status
    resp.is_success = 200 <= status < 300
    return resp


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses,expected_ok,expected_calls", [
    ([503, 502, 200], True, 3),    # transient server errors are retried
    ([429, 200], True, 2),         # rate limited: retried
    ([400], False, 1),             # rejected by the receiver: not retried
    ([500, 500, 500], False, 3),   # gives up after WEBHOOK_MAX_ATTEMPTS
])
async def test_webhook_retries_with_backoff(statuses, expected_ok, expected_calls):
    import httpx
    from domains.notifications.infrastructure.channels.webhook_channel import SIGNATURE_HEADER, sign_payload

    rule, event = _webhook_rule_and_event()
    adapter = WebhookNotificationChannelAdapter(backoff_base_seconds=0)
    with patch("domains.notifications.infrastructure.channels.webhook_channel.assert_public_https_url"), \
         patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock,
                      side_effect=[_response(s) for s in statuses]) as post:
        ok = await adapter.dispatch(event, rule)

    assert ok is expected_ok
    assert post.await_count == expected_calls
    sent = post.await_args.kwargs
    assert sent["headers"][SIGNATURE_HEADER] == sign_payload("s3cret", sent["content"])


@pytest.mark.asyncio
async def test_webhook_network_errors_are_retried():
    import httpx
    rule, event = _webhook_rule_and_event()
    adapter = WebhookNotificationChannelAdapter(backoff_base_seconds=0)
    with patch("domains.notifications.infrastructure.channels.webhook_channel.assert_public_https_url"), \
         patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock,
                      side_effect=[httpx.ConnectError("refused"), _response(200)]) as post:
        assert await adapter.dispatch(event, rule) is True
    assert post.await_count == 2


@pytest.mark.asyncio
async def test_webhook_refuses_unsafe_destination_at_delivery():
    rule, event = _webhook_rule_and_event()
    rule.webhook_url = "https://127.0.0.1/hook"
    assert await WebhookNotificationChannelAdapter().dispatch(event, rule) is False


@pytest.mark.asyncio
async def test_email_sends_in_worker_thread_with_escaped_html():
    from types import SimpleNamespace
    from domains.notifications.infrastructure.channels.email_channel import EmailNotificationChannelAdapter

    rule, event = _webhook_rule_and_event()
    rule.email_destination = "trader@example.com"
    event.message = "<script>alert(1)</script>"
    cfg = SimpleNamespace(SmtpHost="smtp.example.com", SmtpPort=587, SmtpUser="", SmtpPassword="",
                          SmtpFromEmail="alerts@example.com", SmtpUseTls=True)
    with patch("domains.notifications.infrastructure.channels.email_channel.get_settings", return_value=cfg), \
         patch("domains.notifications.infrastructure.channels.email_channel.smtplib.SMTP") as smtp:
        assert await EmailNotificationChannelAdapter().dispatch(event, rule) is True
    import email
    sent = email.message_from_string(smtp.return_value.__enter__.return_value.sendmail.call_args[0][2])
    html_part = next(p for p in sent.walk() if p.get_content_type() == "text/html").get_payload()
    assert "<script>" not in html_part and "&lt;script&gt;" in html_part
