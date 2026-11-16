"""Health/readiness response models mirroring app/api/health.py output."""
# ruff: noqa: RUF002  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LiveResponse(BaseModel):
    """Liveness: процесс жив (без проверки зависимостей)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"] = "ok"


class ComponentHealth(BaseModel):
    """Состояние одного компонента (database/redis/storage/ml)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "ok", "latency_ms": 1.83},
                {"status": "ok", "backend": "s3"},
                {"status": "ok", "provider": "mock"},
                {"status": "error", "detail": "connection refused"},
            ]
        }
    )

    status: str = Field(description="ok / error / unavailable (для ML — ok/degraded/unavailable)")
    detail: str | None = Field(default=None, description="Детали ошибки (при отказе)")
    latency_ms: float | None = Field(
        default=None, description="Латентность проверки, мс (database)", examples=[1.83]
    )
    backend: str | None = Field(
        default=None, description="Бэкенд хранилища: s3 / local", examples=["s3"]
    )
    provider: str | None = Field(
        default=None, description="Провайдер ML: mock / http", examples=["mock"]
    )


class ReadyResponse(BaseModel):
    """Readiness: 200, если database/redis/storage в порядке; иначе 503."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "components": {
                        "database": {"status": "ok", "latency_ms": 1.83},
                        "redis": {"status": "ok"},
                        "storage": {"status": "ok", "backend": "s3"},
                        "ml": {"status": "ok", "provider": "mock"},
                    },
                }
            ]
        }
    )

    status: Literal["ok", "not_ready"] = Field(
        description="ok — все критичные компоненты доступны; not_ready — отказ (HTTP 503)"
    )
    components: dict[str, ComponentHealth] = Field(
        description="Состояние компонентов: database, redis, storage, ml"
    )


class HealthResponse(BaseModel):
    """Агрегированное здоровье сервиса с версией и окружением.

    ok — всё в порядке; degraded — критичные компоненты в порядке, но ML деградировал;
    not_ready — отказ критичного компонента (HTTP 503)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "service": "mgts-infra",
                    "version": "0.1.0",
                    "environment": "development",
                    "components": {
                        "database": {"status": "ok", "latency_ms": 1.83},
                        "redis": {"status": "ok"},
                        "storage": {"status": "ok", "backend": "s3"},
                        "ml": {"status": "ok", "provider": "mock"},
                    },
                }
            ]
        }
    )

    status: Literal["ok", "degraded", "not_ready"] = Field(
        description="ok / degraded (ML недоступен) / not_ready (HTTP 503)"
    )
    service: str = Field(description="Имя сервиса", examples=["mgts-infra"])
    version: str = Field(description="Версия приложения", examples=["0.1.0"])
    environment: str = Field(
        description="Окружение: development / production / test", examples=["development"]
    )
    components: dict[str, ComponentHealth] = Field(
        description="Состояние компонентов: database, redis, storage, ml"
    )
