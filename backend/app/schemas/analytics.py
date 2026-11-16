"""Analytics response models mirroring application/services/analytics.py output."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KeyValueCount(BaseModel):
    """Счётчик группы (тип/статус/полоса/severity)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"key": "telecom_well", "count": 42}]}
    )

    key: str | int | None = Field(
        description="Group key (type/status/band/severity); null band possible",
        examples=["telecom_well"],
    )
    count: int = Field(description="Число записей в группе", examples=[42])


class AnalyticsOverview(BaseModel):
    """Сводные счётчики системы и распределения для дашбордов."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assets_total": 137,
                    "observations_total": 1284,
                    "defects_total": 96,
                    "uploads_total": 58,
                    "routes_total": 7,
                    "observations_reviewed": 312,
                    "observations_reviewed_ratio": 0.243,
                    "assets_without_location": 9,
                    "assets_by_type": [
                        {"key": "telecom_well", "count": 61},
                        {"key": "telecom_cabinet", "count": 44},
                        {"key": "pole", "count": 32},
                    ],
                    "assets_by_priority_band": [
                        {"key": "HIGH_PRIORITY", "count": 18},
                        {"key": "MEDIUM_PRIORITY", "count": 57},
                        {"key": "LOW_PRIORITY", "count": 53},
                        {"key": "NEEDS_REVIEW", "count": 9},
                    ],
                    "defects_by_status": [
                        {"key": "OPEN", "count": 41},
                        {"key": "CONFIRMED", "count": 22},
                        {"key": "IN_PROGRESS", "count": 12},
                        {"key": "RESOLVED", "count": 17},
                        {"key": "REJECTED", "count": 4},
                    ],
                    "defects_by_severity": [
                        {"key": 5, "count": 14},
                        {"key": 4, "count": 27},
                        {"key": 3, "count": 38},
                        {"key": 2, "count": 17},
                    ],
                    "jobs_by_status": [
                        {"key": "COMPLETED", "count": 49},
                        {"key": "PARTIALLY_COMPLETED", "count": 6},
                        {"key": "FAILED", "count": 3},
                    ],
                }
            ]
        }
    )

    assets_total: int = Field(description="Всего активов в реестре", examples=[137])
    observations_total: int = Field(description="Всего наблюдений", examples=[1284])
    defects_total: int = Field(description="Всего дефектов", examples=[96])
    uploads_total: int = Field(description="Всего загрузок", examples=[58])
    routes_total: int = Field(description="Всего маршрутов", examples=[7])
    observations_reviewed: int = Field(
        description="Наблюдений с review_status != UNREVIEWED", examples=[312]
    )
    observations_reviewed_ratio: float = Field(
        description="Доля проверенных наблюдений 0–1 (4 знака)", examples=[0.243]
    )
    assets_without_location: int = Field(
        description="Активы без координат (geolocation_status=UNAVAILABLE)", examples=[9]
    )
    assets_by_type: list[KeyValueCount] = Field(description="Распределение активов по типам")
    assets_by_priority_band: list[KeyValueCount] = Field(
        description="Распределение по полосам приоритета (key=null возможен)"
    )
    defects_by_status: list[KeyValueCount] = Field(description="Дефекты по статусам")
    defects_by_severity: list[KeyValueCount] = Field(description="Дефекты по severity 1–5")
    jobs_by_status: list[KeyValueCount] = Field(description="Job'ы по статусам")


class DefectTypeStats(BaseModel):
    """Агрегация по одному типу дефекта."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "defect_type": "missing_cover",
                    "count": 14,
                    "avg_severity": 4.8,
                    "confirmed_count": 6,
                }
            ]
        }
    )

    defect_type: str = Field(description="Тип дефекта", examples=["missing_cover"])
    count: int = Field(description="Число дефектов этого типа", examples=[14])
    avg_severity: float | None = Field(description="Средняя тяжесть", examples=[4.8])
    confirmed_count: int = Field(description="Из них в статусе CONFIRMED", examples=[6])


class DefectsAnalytics(BaseModel):
    """Агрегация дефектов по типам + счётчик открытых высоких severity."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "by_type": [
                        {
                            "defect_type": "missing_cover",
                            "count": 14,
                            "avg_severity": 4.8,
                            "confirmed_count": 6,
                        },
                        {
                            "defect_type": "cabinet_door_open",
                            "count": 21,
                            "avg_severity": 3.0,
                            "confirmed_count": 9,
                        },
                    ],
                    "open_high_severity_count": 11,
                }
            ]
        }
    )

    by_type: list[DefectTypeStats] = Field(description="Статистика по типам дефектов")
    open_high_severity_count: int = Field(
        description="Дефекты OPEN/CONFIRMED с severity ≥ 4 (очередь срочных работ)",
        examples=[11],
    )


class AreaBoundingBox(BaseModel):
    """Границы исследуемой зоны (демо-зона из настроек DEMO_AREA_BBOX)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "min_longitude": 37.55,
                    "min_latitude": 55.7,
                    "max_longitude": 37.7,
                    "max_latitude": 55.8,
                }
            ]
        }
    )

    min_longitude: float = Field(description="Западная граница (долгота)", examples=[37.55])
    min_latitude: float = Field(description="Южная граница (широта)", examples=[55.7])
    max_longitude: float = Field(description="Восточная граница (долгота)", examples=[37.7])
    max_latitude: float = Field(description="Северная граница (широта)", examples=[55.8])


class CoveredCellCount(BaseModel):
    """Покрытая ячейка сетки: индексы от area_bbox.min_longitude/min_latitude."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"cx": 12, "cy": 27, "observations": 8}]}
    )

    cx: float = Field(description="Индекс столбца ячейки (от min_longitude)", examples=[12])
    cy: float = Field(description="Индекс строки ячейки (от min_latitude)", examples=[27])
    observations: int = Field(description="Геолоцированных наблюдений в ячейке", examples=[8])


class RouteCoverage(BaseModel):
    """Вклад маршрута в покрытие демо-зоны."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "route_id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
                    "name": "Объезд Тверского района, маршрут 1",
                    "observations": 148,
                }
            ]
        }
    )

    route_id: str = Field(description="Идентификатор маршрута (UUID строкой)")
    name: str = Field(description="Название маршрута")
    observations: int = Field(
        description="Geolocated observations inside the configured demo area for this route",
        examples=[148],
    )


class CoverageResponse(BaseModel):
    """Сеточное покрытие зоны обследования: прозрачная эвристика — ячейка покрыта,
    если в неё попало ≥1 геолоцированное наблюдение."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "area_bbox": {
                        "min_longitude": 37.55,
                        "min_latitude": 55.7,
                        "max_longitude": 37.7,
                        "max_latitude": 55.8,
                    },
                    "grid_cell_m": 250.0,
                    "grid_cols": 42,
                    "grid_rows": 45,
                    "total_cells": 1890,
                    "covered_cells": 312,
                    "coverage_ratio": 0.1651,
                    "gap_cells": 1578,
                    "covered_cell_counts": [{"cx": 12, "cy": 27, "observations": 8}],
                    "routes": [
                        {
                            "route_id": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f80",
                            "name": "Объезд Тверского района, маршрут 1",
                            "observations": 148,
                        }
                    ],
                    "note": "heuristic grid coverage over the configured area; "
                    "not a road-network model",
                }
            ]
        }
    )

    area_bbox: AreaBoundingBox = Field(description="Границы исследуемой зоны")
    grid_cell_m: float = Field(description="Размер ячейки сетки в метрах", examples=[250.0])
    grid_cols: int = Field(description="Число столбцов сетки", examples=[42])
    grid_rows: int = Field(description="Число строк сетки", examples=[45])
    total_cells: int = Field(description="Всего ячеек", examples=[1890])
    covered_cells: int = Field(description="Покрытых ячеек (≥1 наблюдение)", examples=[312])
    coverage_ratio: float = Field(description="Доля покрытия 0–1", examples=[0.1651])
    gap_cells: int = Field(description="Непокрытых ячеек (пробелы обследования)", examples=[1578])
    covered_cell_counts: list[CoveredCellCount] = Field(
        description="Покрытые ячейки с числом наблюдений"
    )
    routes: list[RouteCoverage] = Field(description="Вклад маршрутов в покрытие")
    note: str = Field(description="Пояснение методики расчёта покрытия")
