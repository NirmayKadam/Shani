# app/shared/event_bus.py — Redis Pub/Sub event bus
#
# This is the sole communication channel between domains.
# Ingestion publishes → Sentiment subscribes.
# Sentiment publishes → API Gateway subscribes.
# No domain imports another domain directly.

import json
import asyncio
import logging
from typing import Callable, Awaitable, Optional

import redis.asyncio as aioredis

Logger = logging.getLogger(__name__)


class EventBus:
    """
    Thin wrapper around Redis Pub/Sub for inter-domain event communication.

    Usage (publisher):
        bus = EventBus(redis_client)
        await bus.publish("headlines.fetched.NIFTY", {"headline": "...", "score": 0.5})

    Usage (subscriber):
        bus = EventBus(redis_client)
        await bus.subscribe("headlines.fetched.*", my_handler)
        await bus.listen()   # blocking — run in a background task
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._Redis = redis_client
        self._PubSub: Optional[aioredis.client.PubSub] = None
        self._Handlers: dict[str, list[Callable[[str, dict], Awaitable[None]]]] = {}
        self._Listening = False

    # ── Publishing ─────────────────────────────────────────────

    async def publish(self, channel: str, payload: dict) -> int:
        """
        Publish a JSON-serialised event to a Redis Pub/Sub channel.
        Returns the number of subscribers that received the message.
        """
        try:
            message = json.dumps(payload, default=str)
            count = await self._Redis.publish(channel, message)
            Logger.debug("Published to %s (%d subscribers)", channel, count)
            return count
        except Exception as exc:
            Logger.error("Failed to publish to %s: %s", channel, exc)
            return 0

    # ── Subscribing ────────────────────────────────────────────

    async def subscribe(
        self,
        pattern: str,
        handler: Callable[[str, dict], Awaitable[None]]
    ) -> None:
        """
        Register a handler for a channel pattern.
        Patterns use Redis glob syntax: headlines.fetched.* matches
        headlines.fetched.NIFTY, headlines.fetched.RELIANCE, etc.

        The handler signature is: async def handler(channel: str, payload: dict) -> None
        """
        if pattern not in self._Handlers:
            self._Handlers[pattern] = []
        self._Handlers[pattern].append(handler)
        Logger.info("Registered handler for pattern: %s", pattern)

    async def listen(self) -> None:
        """
        Start listening for subscribed patterns. This is blocking —
        run it in an asyncio background task.

        Calls all registered handlers when a matching message arrives.
        """
        if not self._Handlers:
            Logger.warning("EventBus.listen() called with no handlers registered")
            return

        self._PubSub = self._Redis.pubsub()

        # Subscribe to all registered patterns
        for pattern in self._Handlers:
            await self._PubSub.psubscribe(pattern)
            Logger.info("EventBus subscribed to pattern: %s", pattern)

        self._Listening = True
        Logger.info("EventBus listening started")

        try:
            async for message in self._PubSub.listen():
                if message["type"] not in ("pmessage", "message"):
                    continue

                channel = message.get("channel", "")
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8")

                raw_data = message.get("data", "{}")
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")

                try:
                    payload = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    Logger.warning("Non-JSON message on %s: %s", channel, raw_data[:100])
                    continue

                # Match channel against registered patterns and invoke handlers
                matched_pattern = message.get("pattern", "")
                if isinstance(matched_pattern, bytes):
                    matched_pattern = matched_pattern.decode("utf-8")

                handlers = self._Handlers.get(matched_pattern, [])
                for handler in handlers:
                    try:
                        await handler(channel, payload)
                    except Exception as exc:
                        Logger.error(
                            "Handler error for %s on channel %s: %s",
                            handler.__name__, channel, exc, exc_info=True
                        )
        except asyncio.CancelledError:
            Logger.info("EventBus listen cancelled")
        except Exception as exc:
            Logger.error("EventBus listen error: %s", exc, exc_info=True)
        finally:
            self._Listening = False
            if self._PubSub:
                await self._PubSub.punsubscribe()
                await self._PubSub.aclose()
                Logger.info("EventBus listener stopped")

    async def stop(self) -> None:
        """Stop the listener gracefully."""
        self._Listening = False
        if self._PubSub:
            await self._PubSub.punsubscribe()
            await self._PubSub.aclose()
            self._PubSub = None
        Logger.info("EventBus stopped")
