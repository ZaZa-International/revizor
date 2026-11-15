"""Request context middleware: request/correlation IDs, access logs, HTTP metrics."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core import metrics
from app.core.logging import actor_id_var, job_id_var, request_id_var

logger = structlog.get_logger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        job_token = job_id_var.set(None)
        actor_token = actor_id_var.set(None)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed", method=request.method, path=request.url.path)
            raise
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get("route")
            path_template = getattr(route, "path", request.url.path)
            metrics.HTTP_LATENCY.labels(request.method, path_template).observe(duration)
            request_id_var.reset(token)
            job_id_var.reset(job_token)
            actor_id_var.reset(actor_token)
            structlog.contextvars.unbind_contextvars("request_id")
        response.headers["x-request-id"] = request_id
        if request.url.path not in ("/metrics", "/health/live"):
            metrics.HTTP_REQUESTS.labels(
                request.method, path_template, str(response.status_code)
            ).inc()
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )
        return response
