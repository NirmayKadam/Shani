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

App.include_router(sentiment_router)
App.include_router(signals_router)
App.include_router(events_router)
App.include_router(derivatives_router)
App.include_router(predictions_router)

@App.on_event("startup")
async def startup_event():
    # Dependency Injection wireup mapping
    # caching = RedisAdapter()
    # db = TimescaleAdapter()
    # webhook = WebhookAdapter()
    pass

@App.get("/")
def root():
    return {"status": "ok"}
