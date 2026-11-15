"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from starlette.responses import Response

from app.api.errors import register_error_handlers
from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.application.services.auth import AuthService
from app.config import get_settings
from app.core import metrics
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.observability import setup_observability
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
    database = Database(settings)
    storage = build_storage(settings)
    if isinstance(storage, S3Storage):
        await storage.ensure_bucket()
    ml = build_ml_provider(settings)
    queue = build_queue(settings)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
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
    try:
        yield
    finally:
        await ml.close()
        await storage.close()
        await queue.close()
        await redis.aclose()
        await database.dispose()
        logger.info("app_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MGTS Infrastructure Intelligence API",
        version=settings.app_version,
        description=(
            "Backend for drive-by inspection of telecom infrastructure: "
            "asset registry, observations, defects, human review, geospatial analytics. "
            "All endpoints under /api/v1 require a Bearer token except auth/login and health."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    setup_observability(app, settings)

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        try:
            length = await app.state.queue.queue_length()
            metrics.QUEUE_LENGTH.labels(settings.rq_queue_name).set(length)
        except Exception:
            logger.debug("queue_length_scrape_failed")
        return Response(content=generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
