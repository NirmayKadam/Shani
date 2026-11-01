import asyncio
import logging
import os
from typing import Optional
from redis.asyncio import Redis

from domains.notifications.infrastructure.persistence.alert_repository import PostgresAlertRuleRepository
from domains.notifications.infrastructure.channels.websocket_channel import WebSocketNotificationChannelAdapter
from domains.notifications.infrastructure.channels.webhook_channel import WebhookNotificationChannelAdapter
from domains.notifications.infrastructure.channels.email_channel import EmailNotificationChannelAdapter
from domains.notifications.application.evaluate_alerts_service import EvaluateAlertsService
from domains.notifications.domain.value_objects import DeliveryChannel
from shared.constants import Streams, StreamGroups
from shared.infrastructure.event_bus import EventBus
from shared.infrastructure.event_bus.consumer import run_durable_consumer

logger = logging.getLogger("notification_subscriber")


class NotificationStreamSubscriber:
    """Background consumer daemon listening to Redis Streams and evaluating active alert rules."""

    def __init__(self, redis_client: Redis, repository: Optional[PostgresAlertRuleRepository] = None):
        self.redis = redis_client
        self.consume_stream = Streams.OPTIONS_PRICED
        self.repo = repository or PostgresAlertRuleRepository()
        self.channels = {
            DeliveryChannel.WEBSOCKET: WebSocketNotificationChannelAdapter(EventBus(redis_client)),
            DeliveryChannel.WEBHOOK: WebhookNotificationChannelAdapter(),
            DeliveryChannel.EMAIL: EmailNotificationChannelAdapter(),
        }
        self.evaluator = EvaluateAlertsService(repository=self.repo, channels=self.channels)

    async def start_consuming(self, stop_event: Optional[asyncio.Event] = None):
        """At-least-once: priced chains published while this process is down are evaluated after
        restart. Redelivery is safe because a rule fires only on a recorded state transition."""
        logger.info(f"Notification Stream Subscriber listening on stream '{self.consume_stream}'...")
        try:
            await run_durable_consumer(
                self.redis,
                stream=self.consume_stream,
                group=StreamGroups.ALERT_EVALUATION,
                dlq_stream=Streams.OPTIONS_PRICED_DLQ,
                handler=self.process_event,
                max_retries=5,
                stop_event=stop_event,
            )
        except asyncio.CancelledError:
            logger.info("Notification Stream Subscriber stopping...")

    async def process_event(self, parsed: dict):
        """Evaluate one priced-chain event (the dict published by the pricing subscriber)."""
        symbol = parsed.get("symbol")
        if not symbol:
            return

        # Rules are symbol-level: one evaluation per priced chain, against the underlying's
        # spot price and the at-the-money IV (percent). Per-strike premiums are never used.
        snapshot = {
            "spot_price": parsed.get("spot_price"),
            "atm_iv_pct": parsed.get("atm_iv_pct"),
        }
        await self.evaluator.evaluate_tick_event(symbol, snapshot)


async def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = Redis.from_url(redis_url)
    try:
        subscriber = NotificationStreamSubscriber(redis_client)
        await subscriber.start_consuming()
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
