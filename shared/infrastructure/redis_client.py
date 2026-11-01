"""
File Overview: Shared Redis client management for both asynchronous and synchronous contexts.

All Functions/Classes:
- get_redis_client: Async Redis client for the running event loop. Data: App Config -> Async Redis.
- close_redis_client: Gracefully shuts down the current loop's client. Data: Active Client -> Closed.
- get_redis_client_sync: Returns synchronous Redis client. Data: App Config -> Sync Redis.

An asyncio Redis connection pool belongs to the event loop that created it, and this process
can run several loops (one per Celery worker thread). Clients are therefore kept per loop.

Endpoints/APIs: None

Database Tables: None
"""
import asyncio
import logging
import time
import weakref
from dataclasses import dataclass, field

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# After a failed ping, wait this long before pinging again instead of pinging on every call.
_PING_BACKOFF_SECONDS = 5.0


@dataclass
class _LoopRedis:
    client: aioredis.Redis
    healthy: bool = False
    last_ping: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopRedis]" = weakref.WeakKeyDictionary()
_redis_sync_client = None


def _new_client() -> aioredis.Redis:
    from app.config import get_settings
    cfg = get_settings()
    return aioredis.from_url(
        cfg.RedisUrl,
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=5,
        # Bound every command; blocking reads (XREAD BLOCK) set their own longer timeout.
        socket_timeout=15,
        socket_keepalive=True,
        retry_on_timeout=True,
    )


async def get_redis_client() -> aioredis.Redis:
    """
    Return the async Redis client for the running event loop.
    Creates it on first use in that loop; while Redis is unreachable it re-pings at most
    every few seconds and still returns the client (callers handle command errors).
    """
    loop = asyncio.get_running_loop()
    entry = _clients.get(loop)
    if entry is None:
        entry = _clients.setdefault(loop, _LoopRedis(client=_new_client()))
    if entry.healthy:
        return entry.client

    async with entry.lock:
        now = time.monotonic()
        if not entry.healthy and now - entry.last_ping >= _PING_BACKOFF_SECONDS:
            entry.last_ping = now
            try:
                await entry.client.ping()
                entry.healthy = True
                logger.info("Redis connected")
            except (aioredis.ConnectionError, aioredis.RedisError, OSError) as exc:
                logger.error("Redis connection failed: %s  — continuing without Redis", exc)
    return entry.client


async def close_redis_client() -> None:
    """Graceful shutdown of the current loop's client — call from FastAPI lifespan shutdown."""
    entry = _clients.pop(asyncio.get_running_loop(), None)
    if entry is not None:
        try:
            await entry.client.aclose()
            logger.info("Redis client closed")
        except Exception as exc:
            logger.error("Error closing Redis client: %s", exc)


# Backward-compatible alias
CloseRedisClient = close_redis_client


def get_redis_client_sync():
    """
    Returns a sync Redis client connection.
    """
    global _redis_sync_client
    if _redis_sync_client is not None:
        return _redis_sync_client

    from app.config import get_settings
    cfg = get_settings()
    import redis
    _redis_sync_client = redis.Redis.from_url(cfg.RedisUrl, decode_responses=True)
    return _redis_sync_client
