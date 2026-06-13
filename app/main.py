"""
File Overview: Entry point for FastAPI application. Sets up middleware, lifespan hooks,
and includes domain routers following hexagonal architecture.

All Functions/Classes:
- lifespan: Manages app lifecycle. Data: startup -> warm Redis/DB connections, shutdown -> close pools.
- root: Health check endpoint. Data: None -> status dict.

Endpoints/APIs:
- /: root (health check)
- /v1/signals: signals_router
- /ws/{symbol}: events_router (WebSocket)
- /v1/derivatives: derivatives_router
- /v1/predictions: predictions_router
- /v1/symbols: symbols_router
- /v1/ingestion/nse: nse_options_router

Database Tables:
- None directly. Initializes connections for Redis and TimescaleDB.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Domain routers
from domains.analytics.api.signals_router_api import router as signals_router
from domains.analytics.api.events_router_api import router as events_router
from domains.analytics.api.derivatives_router_api import router as derivatives_router
from domains.analytics.api.predictions_router_api import router as predictions_router
from domains.analytics.api.symbols_router_api import router as symbols_router
from domains.analytics.api.pricer_router_api import router as pricer_router
from domains.ingestion.api.nse_options_router_api import nse_options_router_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifecycle: warm connections on startup, close on shutdown."""
    from shared.infrastructure.redis_client import get_redis_client, close_redis_client
    from shared.infrastructure.database import close_database_pool

    # Startup: warm Redis connection pool
    try:
        await get_redis_client()
        logger.info("Redis connection warmed during startup")
    except Exception as exc:
        logger.warning("Redis warmup failed (will retry on first use): %s", exc)

    # Startup: initialize NSE httpx client for option chain fetching
    try:
        from domains.ingestion.api.nse_options_router_api import startup_nse_client
        await startup_nse_client()
        logger.info("NSE httpx client initialized during startup")
    except Exception as exc:
        logger.warning("NSE client startup failed (will lazy-init on first use): %s", exc)

    # Startup: Warm CNN Volatility Predictor Model
    try:
        import asyncio
        from domains.analytics.api.predictions_router_api import _get_predictor
        await asyncio.to_thread(_get_predictor)
        logger.info("CNN Volatility Predictor warmed during startup")
    except Exception as exc:
        logger.warning("CNN Volatility Predictor warmup failed: %s", exc)

    yield

    # Shutdown: close NSE httpx client
    try:
        from domains.ingestion.api.nse_options_router_api import shutdown_nse_client
        await shutdown_nse_client()
    except Exception as exc:
        logger.warning("NSE client shutdown error: %s", exc)

    # Shutdown: close connection pools
    await close_redis_client()
    await close_database_pool()
    logger.info("All connection pools closed")


app = FastAPI(title="AlphaStreams DDD Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(signals_router, prefix="/v1")
app.include_router(events_router, prefix="/v1")
app.include_router(derivatives_router, prefix="/v1")
app.include_router(predictions_router, prefix="/v1")
app.include_router(symbols_router, prefix="/v1")
app.include_router(pricer_router, prefix="/v1")
app.include_router(nse_options_router_api, prefix="/v1/ingestion")


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")