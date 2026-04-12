# app/Main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.Infrastructure.RedisClient import GetRedisClient, CloseRedisClient
from app.Infrastructure.DatabaseClient import GetDatabasePool, CloseDatabasePool
from app.Analytics.Routers.SentimentRouter import Router as SentimentRouter
from app.Analytics.Routers.SignalsRouter import Router as SignalsRouter
from app.Analytics.Routers.EventsRouter import Router as EventsRouter
from app.Analytics.Routers.DerivativesRouter import Router as DerivativesRouter
from app.Analytics.Routers.PredictionsRouter import Router as PredictionsRouter

Logger = logging.getLogger(__name__)

@asynccontextmanager
async def Lifespan(App: FastAPI):
    """
    Startup & Shutdown lifecycle hook.
    Replaces deprecated @app.on_event("startup") and @app.on_event("shutdown").
    """
    # Initialize connection pools on startup
    Logger.info("Starting up AlphaStreams...")
    await GetRedisClient()
    await GetDatabasePool()
    
    yield  # Application is running here
    
    # Close connection pools on shutdown
    Logger.info("Shutting down AlphaStreams...")
    await CloseRedisClient()
    await CloseDatabasePool()

App = FastAPI(
    title="AlphaStreams", 
    version="1.0.0",
    lifespan=Lifespan
)

@App.get("/health")
async def Health():
    return {"status": "ok"}

App.include_router(
    SentimentRouter,
    prefix="/v1/sentiment",
    tags=["Sentiment Insights"]
)
App.include_router(
    SignalsRouter,
    prefix="/v1/signals",
    tags=["Trading Signals"]
)
App.include_router(
    EventsRouter,
    prefix="/v1/events",
    tags=["Historical Events"]
)
App.include_router(
    DerivativesRouter,
    prefix="/v1/derivatives",
    tags=["Derivatives Analytics"]
)
App.include_router(
    PredictionsRouter,
    prefix="/v1/predictions",
    tags=["Machine Learning Forecasts"]
)
