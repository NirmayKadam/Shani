# app/shared/redis_client.py — Async Redis with shared connection pool

import logging
from typing import Optional

import redis.asyncio as aioredis

Logger = logging.getLogger(__name__)

# ── Module-level singleton ──────────────────────────────────────
_RedisClient: Optional[aioredis.Redis] = None


async def GetRedisClient() -> aioredis.Redis:
    """
    Return the shared async Redis client.
    Creates the connection pool on first call; reuses it thereafter.
    """
    global _RedisClient

    if _RedisClient is not None:
        return _RedisClient

    from app.config import GetSettings
    Cfg = GetSettings()

    try:
        _RedisClient = aioredis.from_url(
            Cfg.RedisUrl,
            decode_responses=True,
            max_connections=20,
        )
        await _RedisClient.ping()
        Logger.info("Redis connected  (%s)", Cfg.RedisUrl)
    except (aioredis.ConnectionError, aioredis.RedisError, OSError) as Exc:
        Logger.error("Redis connection failed: %s  — continuing without Redis", Exc)
        if _RedisClient is None:
            _RedisClient = aioredis.from_url(
                Cfg.RedisUrl,
                decode_responses=True,
                max_connections=20,
            )

    return _RedisClient


async def CloseRedisClient() -> None:
    """Graceful shutdown — call from FastAPI's shutdown event."""
    global _RedisClient

    if _RedisClient is not None:
        try:
            await _RedisClient.aclose()
            Logger.info("Redis client closed")
        except Exception as Exc:
            Logger.error("Error closing Redis client: %s", Exc)
        finally:
            _RedisClient = None
