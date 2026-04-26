import logging
from fastapi import FastAPI
from domains.analytics.api.sentiment_router import router as sentiment_router
from domains.analytics.api.signals_router import router as signals_router
from domains.analytics.api.events_router import router as events_router
from domains.analytics.api.derivatives_router import router as derivatives_router
from domains.analytics.api.predictions_router import router as predictions_router
from domains.ingestion.api.nse_options_router import nse_options_router

# Adapters
from domains.analytics.infrastructure.adapters.outbound.redis_adapter import redis_adapter
from domains.analytics.infrastructure.adapters.outbound.timescale_adapter import timescale_adapter
from domains.analytics.infrastructure.adapters.outbound.webhook_adapter import webhook_adapter

logging.basicConfig(level=logging.INFO)

App = FastAPI(title="AlphaStreams DDD Engine")

App.include_router(sentiment_router, prefix="/v1")
App.include_router(signals_router, prefix="/v1")
App.include_router(events_router, prefix="/v1")
App.include_router(derivatives_router, prefix="/v1")
App.include_router(predictions_router, prefix="/v1")
App.include_router(nse_options_router, prefix="/v1/ingestion")

@App.on_event("startup")
async def startup_event():
    import os
    from domains.analytics.infrastructure.adapters.outbound.redis_adapter import redis_adapter
    from domains.analytics.infrastructure.adapters.outbound.timescale_adapter import timescale_adapter
    from domains.analytics.infrastructure.adapters.outbound.webhook_adapter import webhook_adapter

    caching = redis_adapter(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    db = timescale_adapter(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/NexusQuantDB"))
    webhook = webhook_adapter(os.getenv("WEBHOOK_URL", ""))


@App.get("/")
def root():
    return {"status": "ok"}
