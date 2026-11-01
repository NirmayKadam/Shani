"""
File Overview: Shared async PostgreSQL connection pool management using asyncpg.

All Functions/Classes:
- get_database_pool: Pool for the running event loop. Data: App Config -> PostgreSQL Pool.
- close_database_pool: Gracefully shuts down the current loop's pool. Data: Active Pool -> Closed Pool.

An asyncpg pool can only be used from the loop that created it, and this process can run
several loops (one per Celery worker thread), so pools are kept per loop. Creation is locked
so concurrent first calls in one loop share a single pool.

Endpoints/APIs: None

Database Tables:
- Reads from database configuration (NexusQuantDB).
"""
import asyncio
import logging
import weakref
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_pools: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncpg.Pool]" = weakref.WeakKeyDictionary()
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


async def get_database_pool() -> asyncpg.Pool:
    """Return the asyncpg pool for the running event loop, creating it once per loop."""
    loop = asyncio.get_running_loop()
    pool: Optional[asyncpg.Pool] = _pools.get(loop)
    if pool is not None:
        return pool

    lock = _locks.setdefault(loop, asyncio.Lock())
    async with lock:
        pool = _pools.get(loop)
        if pool is not None:
            return pool

        from app.config import get_settings
        cfg = get_settings()
        try:
            pool = await asyncpg.create_pool(
                dsn=cfg.DatabaseUrl,
                min_size=2,
                max_size=10,
                command_timeout=30,
                max_inactive_connection_lifetime=300,
            )
        except Exception as error:
            logger.error("PostgreSQL connection failed: %s", error)
            raise
        _pools[loop] = pool
        logger.info("PostgreSQL connection pool created")
        return pool


async def close_database_pool() -> None:
    """Graceful shutdown of the current loop's pool — call from FastAPI lifespan shutdown."""
    pool = _pools.pop(asyncio.get_running_loop(), None)
    if pool is not None:
        try:
            await pool.close()
            logger.info("PostgreSQL connection pool closed")
        except Exception as error:
            logger.error("Error closing database pool: %s", error)


# Backward-compatible aliases
GetDatabasePool = get_database_pool
CloseDatabasePool = close_database_pool
