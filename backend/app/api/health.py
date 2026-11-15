"""Health and readiness endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict:
    return {"status": "ok"}


async def _check_components(request: Request) -> dict:
    settings = get_settings()
    components: dict[str, dict] = {}
    start = time.perf_counter()
    try:
        async with request.app.state.database.session() as session:
            await session.execute(text("SELECT 1"))
        components["database"] = {"status": "ok"}
    except Exception as exc:
        components["database"] = {"status": "error", "detail": str(exc)[:200]}
    components["database"]["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    try:
        await request.app.state.redis.ping()
        components["redis"] = {"status": "ok"}
    except Exception as exc:
        components["redis"] = {"status": "error", "detail": str(exc)[:200]}
    try:
        await request.app.state.storage.exists("__healthcheck_probe__")
        components["storage"] = {"status": "ok", "backend": settings.storage_backend}
    except Exception as exc:
        components["storage"] = {"status": "error", "detail": str(exc)[:200]}
    try:
        ml_health = await request.app.state.ml.health()
        components["ml"] = {"status": ml_health.status, "provider": ml_health.provider}
    except Exception as exc:
        components["ml"] = {"status": "unavailable", "detail": str(exc)[:200]}
    return components


@router.get("/health/ready", summary="Readiness probe (DB, Redis, storage)")
async def ready(request: Request) -> JSONResponse:
    components = await _check_components(request)
    critical = ("database", "redis", "storage")
    ok = all(components[name]["status"] == "ok" for name in critical)
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "not_ready", "components": components},
    )


@router.get("/health", summary="Aggregate health with component details")
async def health(request: Request) -> JSONResponse:
    settings = get_settings()
    components = await _check_components(request)
    critical = ("database", "redis", "storage")
    ok = all(components[name]["status"] == "ok" for name in critical)
    degraded = ok and components.get("ml", {}).get("status") not in ("ok", None)
    status = "ok" if ok and not degraded else ("degraded" if ok else "not_ready")
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": status,
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
            "components": components,
        },
    )
