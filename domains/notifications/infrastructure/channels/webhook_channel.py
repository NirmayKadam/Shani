import asyncio
import logging
import hmac
import hashlib
import json
import httpx

from app.config.settings import get_settings
from shared.utils.url_safety import UnsafeUrlError, assert_public_https_url
from domains.notifications.domain.entities import NotificationEvent, AlertRule
from domains.notifications.ports.interface.outbound.i_notification_channel import (
    INotificationChannelAdapterPort,
)

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-AlphaStreams-Signature"


def sign_payload(secret: str, body: bytes) -> str:
    """Hex HMAC-SHA256 of the raw request body; receivers recompute it with their secret."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class WebhookNotificationChannelAdapter(INotificationChannelAdapterPort):
    """Outbound adapter delivering alert payloads via HTTP POST to user webhooks."""

    def __init__(self, timeout_seconds: float = 5.0):
        self._timeout = timeout_seconds

    async def dispatch(self, event: NotificationEvent, rule: AlertRule) -> bool:
        if not rule.webhook_url:
            logger.warning(f"Webhook channel invoked for rule {rule.id} but webhook_url is missing")
            return False

        # Re-check at delivery time: the hostname may have been re-pointed since creation.
        try:
            await asyncio.to_thread(assert_public_https_url, rule.webhook_url, get_settings().WebhookAllowPrivate)
        except UnsafeUrlError as exc:
            logger.error("Refusing webhook delivery for rule %s: %s", rule.id, exc)
            return False

        payload = {
            "event_id": str(event.id),
            "rule_id": str(event.rule_id),
            "symbol": event.symbol,
            "condition": event.condition_type.value,
            "value": event.triggered_value,
            "threshold": event.threshold,
            "message": event.message,
            "timestamp": event.timestamp.isoformat(),
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AlphaStreams-Alerts/2.0",
        }
        if rule.webhook_secret:
            headers[SIGNATURE_HEADER] = sign_payload(rule.webhook_secret, body_bytes)
        else:
            # Rules created before per-rule secrets cannot be signed meaningfully.
            logger.warning("Rule %s has no webhook secret; delivering unsigned", rule.id)

        try:
            # Redirects are not followed: a redirect could point at an internal address.
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                resp = await client.post(rule.webhook_url, content=body_bytes, headers=headers)
                if resp.is_success:
                    logger.info(f"Webhook notification delivered for event {event.id} to {rule.webhook_url}")
                    return True
                else:
                    logger.error(f"Webhook POST failed status={resp.status_code} for {rule.webhook_url}")
                    return False
        except Exception as ex:
            logger.error(f"Webhook HTTP error for {rule.webhook_url}: {ex}")
            return False
