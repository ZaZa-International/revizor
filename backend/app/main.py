"""FastAPI application factory and lifespan."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import func, select
from starlette.responses import Response

from app.api.docs import OPENAPI_TAGS
from app.api.docs import router as docs_router
from app.api.errors import register_error_handlers
from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.application.services.auth import AuthService
from app.config import get_settings
from app.core import metrics
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    BodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import setup_observability
from app.domain.enums import JobStatus
from app.infrastructure.database.models.job import ProcessingJob
from app.infrastructure.database.session import Database
from app.infrastructure.ml.factory import build_ml_provider
from app.infrastructure.queue.factory import build_queue
from app.infrastructure.storage.factory import build_storage
from app.infrastructure.storage.s3 import S3Storage

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    async with AsyncExitStack() as stack:
        database = Database(settings)
        stack.push_async_callback(database.dispose)
        storage = build_storage(settings)
        stack.push_async_callback(storage.close)
        if isinstance(storage, S3Storage):
            await storage.ensure_bucket()
        ml = build_ml_provider(settings)
        stack.push_async_callback(ml.close)
        queue = build_queue(settings, database=database)
        stack.push_async_callback(queue.close)
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        stack.push_async_callback(redis.aclose)
        app.state.database = database
        app.state.storage = storage
        app.state.ml = ml
        app.state.queue = queue
        app.state.redis = redis
        async with database.session() as session:
            admin = await AuthService(session, settings).bootstrap_admin()
            await session.commit()
            if admin is not None:
                logger.info("bootstrap_admin_created", username=admin.username)
        logger.info(
            "app_started",
            env=settings.app_env,
            storage=settings.storage_backend,
            ml=settings.ml_provider,
            queue=settings.queue_mode,
        )
        yield
    logger.info("app_stopped")


_API_DESCRIPTION = """\
Backend мониторинга телеком-инфраструктуры МГТС: загрузка изображений/видео проездов →
обработка в worker → ML-детекции → дедупликация физических объектов → реестр
Asset / Observation / Defect → risk scoring → проверка оператором → карта, аналитика и выгрузки.

### Быстрый старт

1. `POST /api/v1/auth/login` с JSON `{"username": "admin", "password": "..."}` →
   `access_token` (JWT, по умолчанию 60 минут).
2. Все запросы (кроме `/auth/login` и `/health*`) выполняются с заголовком
   `Authorization: Bearer <access_token>`. В Swagger UI нажмите **Authorize**.
3. Сквозной сценарий: upload → job → polling → observations → asset → review → map → export
   (см. описания тегов и `docs/api/workflows.md`).

### Роли

`ADMIN`, `OPERATOR`, `SERVICE` — загрузки, jobs, reviews, PATCH, медиафайлы;
`VIEWER` — только чтение, без медиа-ссылок (`image_url`/`crop_url`/`presigned_url` = null).

### Единый формат ошибок

Любая ошибка (включая 422) возвращается как
`{"error": {"code", "message", "details", "request_id"}}` — это **не** дефолтный
FastAPI `HTTPValidationError`. Коды: `not_found`, `validation_error`,
`authentication_failed`, `permission_denied`, `conflict`, `invalid_job_state`,
`idempotency_conflict`, `rate_limited` (с `Retry-After`), `storage_unavailable`,
`ml_unavailable`, `ml_timeout`, `ml_contract_violation`, `internal_error`.
Каждый ответ несёт заголовок `x-request-id`.

### Общие правила

- Пагинация: `page` (≥1), `page_size` (1–100, по умолчанию 20); envelope
  `{items, total, page, page_size, pages}`. Сортировка — только по whitelist `sort_by`.
- География: координаты всегда `(longitude, latitude)`, WGS84; bbox-фильтр
  `min_lon,min_lat,max_lon,max_lat`; расстояния в метрах (PostGIS geography).
- Идемпотентность мутаций: заголовок `Idempotency-Key` (≤128 символов) для
  POST uploads/jobs/reviews/routes; повтор возвращает сохранённый ответ,
  другой payload с тем же ключом → 409 `idempotency_conflict`.
- Оптимистичная блокировка Asset: `expected_version` в PATCH → 409 при конфликте.

### Документация

- [docs/api/overview.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/overview.md) — обзор портала
- [docs/api/authentication.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/authentication.md) — аутентификация и роли
- [docs/api/errors.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/errors.md) — коды ошибок
- [docs/api/pagination-filtering.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/pagination-filtering.md) — пагинация и фильтры
- [docs/api/geospatial.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/geospatial.md) — геоданные и GeoJSON
- [docs/api/upload-and-processing.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/upload-and-processing.md) — загрузка и обработка
- [docs/api/workflows.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/api/workflows.md) — сквозные сценарии
- [docs/integrations/frontend-contract.md](https://github.com/ZaZa-International/revizor/\
blob/main/docs/integrations/frontend-contract.md) — контракт frontend
"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MGTS Infrastructure Intelligence API",
        version=settings.app_version,
        debug=settings.debug,
        description=_API_DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
        servers=[{"url": "http://localhost:8000", "description": "Локальная среда разработки"}],
        contact={"name": "MGTS Infrastructure Intelligence Team"},
        license_info={"name": "MIT"},
        generate_unique_id_function=lambda route: route.name,
    )
    # add_middleware prepends: last added runs outermost.
    # Execution order (outermost -> innermost): BodyLimit -> SecurityHeaders ->
    # RequestContext -> CORS -> route.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(docs_router)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parent / "static"),
        name="static",
    )
    setup_observability(app, settings)

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics_endpoint() -> Response:
            try:
                length = await app.state.queue.queue_length()
                metrics.QUEUE_LENGTH.labels(settings.rq_queue_name).set(length)
            except Exception:
                logger.debug("queue_length_scrape_failed")
            try:
                async with app.state.database.session() as session:
                    active = (
                        await session.execute(
                            select(func.count(ProcessingJob.id)).where(
                                ProcessingJob.status == JobStatus.PROCESSING
                            )
                        )
                    ).scalar_one()
                    metrics.JOBS_ACTIVE.set(active)
            except Exception:
                logger.debug("jobs_active_scrape_failed")
            return Response(
                content=generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST
            )

    return app


app = create_app()
