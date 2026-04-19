import logging
from fastapi import FastAPI
from domains.analytics.api.SentimentRouter import router as sentiment_router
from domains.analytics.api.SignalsRouter import router as signals_router
from domains.analytics.api.EventsRouter import router as events_router
from domains.analytics.api.DerivativesRouter import router as derivatives_router
from domains.analytics.api.PredictionsRouter import router as predictions_router

# Adapters
from domains.analytics.adapters.outbound.RedisAdapter import RedisAdapter
from domains.analytics.adapters.outbound.TimescaleAdapter import TimescaleAdapter
from domains.analytics.adapters.outbound.WebhookAdapter import WebhookAdapter

logging.basicConfig(level=logging.INFO)

App = FastAPI(title="AlphaStreams DDD Engine")

App.include_router(sentiment_router, prefix="/v1")
App.include_router(signals_router, prefix="/v1")
App.include_router(events_router, prefix="/v1")
App.include_router(derivatives_router, prefix="/v1")
App.include_router(predictions_router, prefix="/v1")

@App.on_event("startup")
async def startup_event():
    import os
    from domains.analytics.adapters.outbound.RedisAdapter import RedisAdapter
    from domains.analytics.adapters.outbound.TimescaleAdapter import TimescaleAdapter
    from domains.analytics.adapters.outbound.WebhookAdapter import WebhookAdapter

    caching = RedisAdapter(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    db = TimescaleAdapter(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/NexusQuantDB"))
    webhook = WebhookAdapter(os.getenv("WEBHOOK_URL", ""))


@App.get("/")
def root():
    return {"status": "ok"}
