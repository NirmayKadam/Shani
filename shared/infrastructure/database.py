"""
File Overview: Shared async PostgreSQL connection pool management using asyncpg.

All Functions/Classes:
- get_database_pool: Singleton getter for connection pool. Data: App Config -> PostgreSQL Pool.
- close_database_pool: Gracefully shuts down connection pool. Data: Active Pool -> Closed Pool.

Endpoints/APIs: None

Database Tables:
- Reads from database configuration (NexusQuantDB).
"""
import logging
import asyncpg
from typing import Optional

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_database_pool() -> asyncpg.Pool:
    """
    Returns the shared asyncpg connection pool.
    Creates it on first call, reuses it forever.
    """
    global _pool

    if _pool is not None:
        return _pool

    from app.config import get_settings
    cfg = get_settings()

    try:
        _pool = await asyncpg.create_pool(
            dsn=cfg.DatabaseUrl,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("PostgreSQL connection pool created")
    except Exception as error:
        logger.error("PostgreSQL connection failed: %s", error)
        raise

    return _pool


async def close_database_pool() -> None:
    """Graceful shutdown — call from FastAPI lifespan shutdown."""
    global _pool

    if _pool is not None:
        try:
            await _pool.close()
            logger.info("PostgreSQL connection pool closed")
        except Exception as error:
            logger.error("Error closing database pool: %s", error)
        finally:
            _pool = None


# Backward-compatible aliases
GetDatabasePool = get_database_pool
CloseDatabasePool = close_database_pool
