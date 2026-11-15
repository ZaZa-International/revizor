"""Unified error rendering: {"error": {code, message, details, request_id}}."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError, RateLimitError
from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)


def _envelope(code: str, message: str, details: list[dict] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id_var.get(),
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitError):
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", [])),
                "message": err.get("msg", "invalid value"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", "Request validation failed", details),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("integrity_error", error=str(exc.orig)[:300])
        return JSONResponse(
            status_code=409,
            content=_envelope("conflict", "Data conflict (unique or foreign key constraint)"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 401: "authentication_failed", 403: "permission_denied"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "Internal server error"),
        )
