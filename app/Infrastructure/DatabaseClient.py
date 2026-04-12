# app/Infrastructure/DatabaseClient.py
import logging
import asyncpg
from typing import Optional
from app.Config import GetSettings

Logger = logging.getLogger(__name__)

_Pool: Optional[asyncpg.Pool] = None


async def GetDatabasePool() -> asyncpg.Pool:
    """
    Returns the shared asyncpg connection pool.
    Creates it on first call, reuses it forever.
    """
    global _Pool

    if _Pool is not None:
        return _Pool

    Cfg = GetSettings()
    try:
        _Pool = await asyncpg.create_pool(
            dsn=Cfg.DatabaseUrl,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        Logger.info("PostgreSQL connection pool created")
    except Exception as Error:
        Logger.error(f"PostgreSQL connection failed: {Error}")
        raise

    return _Pool


async def CloseDatabasePool() -> None:
    """Graceful shutdown — call from FastAPI shutdown event."""
    global _Pool

    if _Pool is not None:
        try:
            await _Pool.close()
            Logger.info("PostgreSQL connection pool closed")
        except Exception as Error:
            Logger.error(f"Error closing database pool: {Error}")
        finally:
            _Pool = None