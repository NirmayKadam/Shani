"""
File Overview: Shared async PostgreSQL connection pool management using asyncpg.

All Functions/Classes:
- GetDatabasePool: Singleton getter for the connection pool. Data: App Config -> PostgreSQL Pool.
- CloseDatabasePool: Gracefully shuts down the connection pool. Data: Active Pool -> Closed Pool.

Endpoints/APIs:
- None.

Database Tables:
- Reads from database configuration (NexusQuantDB).
"""


import logging
import asyncpg
from typing import Optional

logger = logging.getLogger(__name__)

_Pool: Optional[asyncpg.Pool] = None


async def GetDatabasePool() -> asyncpg.Pool:
    """
    Returns the shared asyncpg connection pool.
    Creates it on first call, reuses it forever.
    """
    global _Pool

    if _Pool is not None:
        return _Pool

    from app.config import get_settings
    Cfg = get_settings()

    try:
        _Pool = await asyncpg.create_pool(
            dsn=Cfg.DatabaseUrl,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        logger.info("PostgreSQL connection pool created")
    except Exception as Error:
        logger.error(f"PostgreSQL connection failed: {Error}")
        raise

    return _Pool


async def CloseDatabasePool() -> None:
    """Graceful shutdown — call from FastAPI shutdown event."""
    global _Pool

    if _Pool is not None:
        try:
            await _Pool.close()
            logger.info("PostgreSQL connection pool closed")
        except Exception as Error:
            logger.error(f"Error closing database pool: {Error}")
        finally:
            _Pool = None
