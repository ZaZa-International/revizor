"""Request context middleware: request/correlation IDs, access logs, HTTP metrics.

Also hosts BodyLimitMiddleware (SEC-1/SEC-2) and SecurityHeadersMiddleware (SEC-13).
Registration order in main.py: BodyLimit outermost, then SecurityHeaders,
then RequestContext, then CORS.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings, get_settings
from app.core import metrics
from app.core.logging import actor_id_var, job_id_var, request_id_var

logger = structlog.get_logger("app.access")

_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
_MAX_REQUEST_ID_LENGTH = 64
_UNMATCHED_PATH_LABEL = "<unmatched>"


class _BodyTooLargeError(Exception):
    """Internal signal: streamed request body exceeded the configured limit."""


class BodyLimitMiddleware:
    """Pure ASGI body-size guard applied before auth and body buffering.

    Rejects early on Content-Length and aborts mid-stream once the counted
    bytes exceed the limit: multipart requests get max_upload_size_bytes plus
    1MB of boundary overhead, everything else max_json_body_bytes.
    """

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = self._settings if self._settings is not None else get_settings()
        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "")
        if content_type.startswith("multipart/"):
            limit = settings.max_upload_size_bytes + _MULTIPART_OVERHEAD_BYTES
        else:
            limit = settings.max_json_body_bytes

        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            if declared_size > limit:
                await self._reject(scope, receive, send, limit)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLargeError:
            if not response_started:
                await self._reject(scope, receive, send, limit)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "payload_too_large",
                    "message": f"Request body exceeds the maximum allowed size of {limit} bytes",
                    "details": [],
                    "request_id": request_id_var.get(),
                }
            },
        )
        await response(scope, receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers; CSP frame-ancestors only on docs UI paths."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        path = request.url.path
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if path.startswith("/docs") or path.startswith("/redoc"):
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = (request.headers.get("x-request-id") or str(uuid.uuid4()))[
            :_MAX_REQUEST_ID_LENGTH
        ]
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
            path_template = getattr(route, "path", None) or _UNMATCHED_PATH_LABEL
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
