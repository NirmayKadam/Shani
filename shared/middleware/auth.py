import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.auth")

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            logger.info("Auth header present in request")
        return await call_next(request)
