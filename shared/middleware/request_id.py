import re
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from shared.logging.logger import set_correlation_id

# Client-supplied ids are echoed into logs and response headers: accept only short, plain ids.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def correlation_id_for(request: Request) -> str:
    """The caller's X-Request-ID / X-Correlation-ID if it is safe to log, else a new UUID."""
    supplied = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or ""
    return supplied if _SAFE_ID.match(supplied) else str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = correlation_id_for(request)
        set_correlation_id(request_id)

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
