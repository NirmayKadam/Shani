# app/main.py — FastAPI application entry point
#
# Registers all domain routers and manages lifecycle hooks.
# uvicorn references: app.main:App

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.shared.redis_client import GetRedisClient, CloseRedisClient
from app.shared.database import GetDatabasePool, CloseDatabasePool

Logger = logging.getLogger(__name__)


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_envelope(*, error: str, code: str, details=None, source: str = "frontend_api") -> dict:
    return {
        "generated_at": _generated_at(),
        "source": source,
        "stale": False,
        "partial": True,
        "error": error,
        "code": code,
        "details": details,
    }


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


@App.exception_handler(RequestValidationError)
async def HandleRequestValidationError(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=_error_envelope(
            error="Request validation failed.",
            code="request_validation_error",
            details=exc.errors(),
            source=str(request.url.path),
        ),
    )


@App.exception_handler(HTTPException)
async def HandleHttpException(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(
            error=str(exc.detail),
            code="http_error",
            details={"status_code": exc.status_code},
            source=str(request.url.path),
        ),
    )


@App.exception_handler(Exception)
async def HandleRuntimeException(request: Request, exc: Exception):
    Logger.error("Unhandled runtime error on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=_error_envelope(
            error="Internal server error.",
            code="runtime_error",
            details={"exception": str(exc)},
            source=str(request.url.path),
        ),
    )


# ── Health Check ────────────────────────────────────────────────

@App.get("/health")
async def Health():
    return {"status": "ok", "version": "2.0.0"}


# ── Register Domain Routers ────────────────────────────────────

from app.domain.frontend_api.interfaces.routers.symbols import Router as SymbolsRouter
from app.domain.frontend_api.interfaces.routers.analyze import Router as AnalyzeRouter
from app.domain.frontend_api.interfaces.routers.websocket import Router as WebSocketRouter

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

# ── Static Files & Dashboard ──────────────────────────────────
import os

_STATIC_PATH = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(_STATIC_PATH):
    os.makedirs(_STATIC_PATH, exist_ok=True)

App.mount("/static", StaticFiles(directory=_STATIC_PATH), name="static")


@App.get("/")
async def Dashboard():
    index_file = os.path.join(_STATIC_PATH, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse(content={"message": "AlphaStreams v2 API is running. UI not found."})
