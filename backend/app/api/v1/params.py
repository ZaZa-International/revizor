"""Shared query-parameter validators and per-resource sort whitelists.

Sort aliases are exposed as Literal types so unknown values fail FastAPI
validation with 422 and the allowed values are visible in OpenAPI.
"""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Header, Query

from app.core.exceptions import ValidationAppError

AssetSort = Literal[
    "created_at", "last_observed_at", "current_priority", "current_severity", "asset_type"
]
JobSort = Literal["created_at", "status", "started_at", "finished_at"]
ObservationSort = Literal["observed_at", "created_at", "detector_confidence"]
DefectSort = Literal["created_at", "last_detected_at", "severity", "status"]
ReviewSort = Literal["reviewed_at", "created_at"]
RouteSort = Literal["created_at", "started_at", "name", "total_distance_m"]

PageQuery = Annotated[int, Query(ge=1, description="Номер страницы, начиная с 1 (по умолчанию 1)")]
PageSizeQuery = Annotated[
    int,
    Query(ge=1, le=100, description="Размер страницы: 1–100 (по умолчанию 20)"),
]
OrderQuery = Annotated[
    Literal["asc", "desc"],
    Query(description="Направление сортировки: asc (по возрастанию) / desc (по убыванию)"),
]
BboxQuery = Annotated[
    str | None,
    Query(
        description="Географический фильтр bbox: `min_lon,min_lat,max_lon,max_lat` "
        "(WGS84, порядок координат lon/lat). Пример: 37.55,55.70,37.70,55.80"
    ),
]
SearchQuery = Annotated[
    str | None,
    Query(
        max_length=128,
        description="Поиск по подстроке (регистронезависимый, ≤128 символов; "
        "LIKE-спецсимволы экранируются)",
    ),
]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        max_length=128,
        description="Ключ идемпотентности (≤128 символов, рекомендуется UUID). "
        "Повтор с тем же ключом и payload возвращает сохранённый ответ (replay); "
        "тот же ключ с другим payload → 409 idempotency_conflict. "
        "Ключи scoped по пользователю и endpoint.",
    ),
]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def validate_date_range(date_from: datetime | None, date_to: datetime | None) -> None:
    if date_from is not None and date_to is not None and _as_utc(date_from) > _as_utc(date_to):
        raise ValidationAppError("date_from must be earlier than or equal to date_to")
