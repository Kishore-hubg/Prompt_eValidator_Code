"""
Request logging middleware.

Logs every inbound HTTP request with method, path, status code, and
wall-clock duration.  Output is structured so it is easy to tail locally
or pipe into any log aggregator (CloudWatch, Datadog, Loki, etc.).

Log format (INFO level):
    METHOD /path/to/endpoint → <status>  (<duration> ms)

Example:
    POST /api/v1/validate → 200  (312.4 ms)
    GET  /api/v1/health   → 200  (1.2 ms)
"""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("prompt_validator.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that emits one log line per HTTP request/response pair."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "%-6s %s → %d  (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
