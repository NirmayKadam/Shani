import asyncio
import hmac
import logging
import uuid
from typing import Optional

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config.settings import get_settings
from shared.auth import AuthError, get_jwt_verifier

logger = logging.getLogger("api.auth")


def _bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    return auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detail})


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware:
    - Internal ingestion routes require INTERNAL_API_KEY (constant-time compare). In production
      the routes are closed when no key is configured.
    - User routes (alert rules) require a verified Supabase JWT; request.state.user_id is the
      token's subject. Without auth configured, development runs anonymously and production
      refuses the request.
    - Everything else is public market data; a valid token, if sent, is still attached.
    """

    PROTECTED_INGESTION_PREFIXES = ("/v1/ingestion/",)
    USER_PREFIXES = ("/v1/notifications/",)

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        path = request.url.path
        request.state.user_id = None
        request.state.user = None

        # 1. Internal ingestion routes
        if any(path.startswith(prefix) for prefix in self.PROTECTED_INGESTION_PREFIXES):
            supplied = request.headers.get("X-Internal-API-Key", "") or request.headers.get("X-API-Key", "") or _bearer_token(request)
            if settings.InternalApiKey:
                if not hmac.compare_digest(supplied.encode(), settings.InternalApiKey.encode()):
                    logger.warning("Unauthorized ingestion access attempt to %s from %s", path,
                                   request.client.host if request.client else "unknown")
                    return _unauthorized("Invalid or missing internal API key")
            elif settings.is_production:
                logger.error("INTERNAL_API_KEY is not set; refusing ingestion route %s", path)
                return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                    content={"detail": "Internal API is not configured"})
            return await call_next(request)

        # 2. User routes and optional identity elsewhere
        verifier = get_jwt_verifier()
        token = _bearer_token(request)
        is_user_route = any(path.startswith(prefix) for prefix in self.USER_PREFIXES)

        if is_user_route and not verifier.configured:
            if settings.is_production:
                logger.error("Supabase auth is not configured; refusing user route %s", path)
                return _unauthorized("Authentication is not configured on this server")
            # Local development without Supabase: anonymous access, rules are not owned.
            return await call_next(request)

        if token and verifier.configured:
            try:
                claims = await asyncio.to_thread(verifier.verify, token)
                request.state.user = claims
                request.state.user_id = _parse_user_id(claims.get("sub"))
            except AuthError as exc:
                if is_user_route:
                    return _unauthorized(str(exc))
                logger.debug("Ignoring invalid token on public route %s: %s", path, exc)

        if is_user_route and request.state.user_id is None:
            return _unauthorized("Authentication required for this operation")

        return await call_next(request)


def _parse_user_id(sub) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(sub))
    except (TypeError, ValueError):
        return None
