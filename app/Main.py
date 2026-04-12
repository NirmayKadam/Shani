# app/main.py — FastAPI application entry point
#
# Registers all domain routers and manages lifecycle hooks.
# uvicorn references: app.main:App

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.shared.redis_client import GetRedisClient, CloseRedisClient
from app.shared.database import GetDatabasePool, CloseDatabasePool

Logger = logging.getLogger(__name__)


@asynccontextmanager
async def Lifespan(application: FastAPI):
    """
    Startup & Shutdown lifecycle hook.
    Initializes connection pools on startup, cleans up on shutdown.
    """
    Logger.info("Starting up AlphaStreams v2...")
    await GetRedisClient()
    await GetDatabasePool()

    yield  # Application is running here

    Logger.info("Shutting down AlphaStreams v2...")
    await CloseRedisClient()
    await CloseDatabasePool()


App = FastAPI(
    title="AlphaStreams",
    version="2.0.0",
    description="Event-driven quantitative sentiment analytics platform",
    lifespan=Lifespan
)


# ── Health Check ────────────────────────────────────────────────

@App.get("/health")
async def Health():
    return {"status": "ok", "version": "2.0.0"}


# ── Register Domain Routers ────────────────────────────────────

from app.domain.api.routers.symbols import Router as SymbolsRouter
from app.domain.api.routers.analyze import Router as AnalyzeRouter
from app.domain.api.routers.websocket import Router as WebSocketRouter

App.include_router(
    SymbolsRouter,
    prefix="/v1",
    tags=["Symbols"]
)

App.include_router(
    AnalyzeRouter,
    prefix="/v1",
    tags=["Analysis"]
)

App.include_router(
    WebSocketRouter,
    tags=["WebSocket"]
)
