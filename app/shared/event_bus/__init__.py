import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

import redis.asyncio as aioredis

Logger = logging.getLogger(__name__)


class EventBus:
    """Redis Pub/Sub event bus for bounded-context integration."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._Redis = redis_client
        self._PubSub: Optional[aioredis.client.PubSub] = None
        self._Handlers: dict[str, list[Callable[[str, dict], Awaitable[None]]]] = {}
        self._Listening = False

    async def publish(self, channel: str, payload: dict) -> int:
        try:
            message = json.dumps(payload, default=str)
            count = await self._Redis.publish(channel, message)
            Logger.debug("Published to %s (%d subscribers)", channel, count)
            return count
        except Exception as exc:
            Logger.error("Failed to publish to %s: %s", channel, exc)
            return 0

    async def subscribe(
        self,
        pattern: str,
        handler: Callable[[str, dict], Awaitable[None]],
    ) -> None:
        if pattern not in self._Handlers:
            self._Handlers[pattern] = []
        self._Handlers[pattern].append(handler)
        Logger.info("Registered handler for pattern: %s", pattern)

    async def listen(self) -> None:
        if not self._Handlers:
            Logger.warning("EventBus.listen() called with no handlers registered")
            return

        self._PubSub = self._Redis.pubsub()
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

                matched_pattern = message.get("pattern", "")
                if isinstance(matched_pattern, bytes):
                    matched_pattern = matched_pattern.decode("utf-8")

                for handler in self._Handlers.get(matched_pattern, []):
                    try:
                        await handler(channel, payload)
                    except Exception as exc:
                        Logger.error(
                            "Handler error for %s on channel %s: %s",
                            handler.__name__,
                            channel,
                            exc,
                            exc_info=True,
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
        self._Listening = False
        if self._PubSub:
            await self._PubSub.punsubscribe()
            await self._PubSub.aclose()
            self._PubSub = None
        Logger.info("EventBus stopped")
