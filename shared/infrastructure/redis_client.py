# shared/infrastructure/redis_client.py — Redis clients (Async & Sync)

import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ── Module-level singleton ──────────────────────────────────────
_RedisClient: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """
    Return the shared async Redis client.
    Creates the connection pool on first call; reuses it thereafter.
    """
    global _RedisClient

    if _RedisClient is not None:
        return _RedisClient

    from app.config import get_settings
    Cfg = get_settings()

    try:
        _RedisClient = aioredis.from_url(
            Cfg.RedisUrl,
            decode_responses=True,
            max_connections=20,
        )
        await _RedisClient.ping()
        logger.info("Redis connected  (%s)", Cfg.RedisUrl)
    except (aioredis.ConnectionError, aioredis.RedisError, OSError) as Exc:
        logger.error("Redis connection failed: %s  — continuing without Redis", Exc)
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
            logger.info("Redis client closed")
        except Exception as Exc:
            logger.error("Error closing Redis client: %s", Exc)
        finally:
            _RedisClient = None

def get_redis_sync():
    """
    Returns a sync Redis client connection.
    """
    from app.config import get_settings
    Cfg = get_settings()
    import redis
    return redis.Redis.from_url(Cfg.RedisUrl, decode_responses=True)
