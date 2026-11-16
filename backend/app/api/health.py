"""Health and readiness endpoints."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.route import DocumentedRoute
from app.config import get_settings
from app.schemas.health import HealthResponse, LiveResponse, ReadyResponse

router = APIRouter(tags=["System & Health"], route_class=DocumentedRoute)


@router.get(
    "/health/live",
    response_model=LiveResponse,
    summary="Liveness-проба: процесс жив",
    description=(
        "Мгновенная проверка жизнеспособности процесса без обращения к зависимостям.\n\n"
        '- **200** — процесс отвечает (`{"status": "ok"}`).\n'
        "- Используется оркестраторами для restart-политик; не требует аутентификации.\n"
        "- Отказ компонентов (БД/Redis/S3/ML) на этот endpoint не влияет — "
        "для готовности используйте `/health/ready`.\n\n"
        "См. docs/api/overview.md."
    ),
)
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


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness-проба: БД, Redis, хранилище",
    description=(
        "Проверка готовности принимать трафик: опрашиваются PostgreSQL (`SELECT 1`), "
        "Redis (`PING`) и хранилище (probe-объект), дополнительно ML.\n\n"
        "- **200** — все критичные компоненты (database, redis, storage) в статусе ok.\n"
        "- **503** — отказ хотя бы одного критичного компонента (`status: not_ready`); "
        "тело ответа содержит статус каждого компонента и латентность проверки БД.\n"
        "- ML не является критичным компонентом: его отказ не даёт 503 "
        "(смотрите агрегированный `/health`).\n"
        "- Не требует аутентификации; пригоден для readiness-проб балансировщика.\n\n"
        "См. docs/api/overview.md."
    ),
    responses={
        503: {
            "model": ReadyResponse,
            "description": "Критичный компонент недоступен (database/redis/storage)",
        }
    },
)
async def ready(request: Request) -> JSONResponse:
    components = await _check_components(request)
    critical = ("database", "redis", "storage")
    ok = all(components[name]["status"] == "ok" for name in critical)
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "not_ready", "components": components},
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Агрегированное здоровье сервиса",
    description=(
        "Полная картина здоровья: имя сервиса, версия, окружение и статусы "
        "компонентов (database, redis, storage, ml).\n\n"
        "- **200** `status: ok` — все компоненты в порядке.\n"
        "- **200** `status: degraded` — критичные компоненты в порядке, "
        "но ML недоступен/деградировал (обработка новых job'ов невозможна).\n"
        "- **503** `status: not_ready` — отказ критичного компонента "
        "(database/redis/storage).\n"
        "- Не требует аутентификации; используется мониторингом и дашбордами.\n\n"
        "См. docs/api/overview.md и docs/api/errors.md."
    ),
    responses={
        503: {
            "model": HealthResponse,
            "description": "Критичный компонент недоступен (database/redis/storage)",
        }
    },
)
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
