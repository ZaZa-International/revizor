"""Analytics API (read-via-service)."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from fastapi import APIRouter

from app.api.route import DocumentedRoute
from app.application.services.analytics import AnalyticsService
from app.dependencies import CurrentUser, SessionDep, SettingsDep
from app.schemas.analytics import AnalyticsOverview, CoverageResponse, DefectsAnalytics

router = APIRouter(prefix="/analytics", tags=["Analytics & Coverage"], route_class=DocumentedRoute)


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    summary="Сводные счётчики и распределения",
    description=(
        "Системная аналитика для дашбордов: одним запросом все ключевые счётчики.\n\n"
        "- **200** — AnalyticsOverview: totals (assets/observations/defects/uploads/"
        "routes), доля проверенных наблюдений (`observations_reviewed_ratio` 0–1), "
        "активы без координат, распределения: активы по типам и полосам приоритета "
        "(key=null возможен), дефекты по статусам и severity, job'ы по статусам.\n\n"
        "Все распределения — списки `{key, count}` (KeyValueCount), готовые для "
        "рендеринга диаграммами. Агрегаты считаются по всей БД без фильтров. "
        "См. docs/api/overview.md."
    ),
)
async def overview(session: SessionDep, settings: SettingsDep, user: CurrentUser) -> dict:
    return await AnalyticsService(session, settings).overview()


@router.get(
    "/defects",
    response_model=DefectsAnalytics,
    summary="Агрегация дефектов по типам",
    description=(
        "Аналитика дефектов для планирования ремонтных работ.\n\n"
        "- **200** — DefectsAnalytics: `by_type` (для каждого типа дефекта: count, "
        "avg_severity, confirmed_count) и `open_high_severity_count` — дефекты "
        "OPEN/CONFIRMED с severity ≥ 4 (очередь срочных работ).\n\n"
        "Типы дефектов — из реестра taxonomy (missing_cover, cabinet_door_open, "
        "pole_tilt, cable_break и др.). См. docs/api/overview.md, docs/api/workflows.md."
    ),
)
async def defects_analytics(session: SessionDep, settings: SettingsDep, user: CurrentUser) -> dict:
    return await AnalyticsService(session, settings).defects_analytics()


@router.get(
    "/coverage",
    response_model=CoverageResponse,
    summary="Сеточное покрытие зоны обследования",
    description=(
        "Покрытие демо-зоны (DEMO_AREA_BBOX) равномерной сеткой ячеек "
        "~COVERAGE_GRID_CELL_M метров (по умолчанию 250 м).\n\n"
        "- **200** — CoverageResponse: `area_bbox`, параметры сетки "
        "(grid_cell_m/cols/rows), total_cells, covered_cells, coverage_ratio (0–1), "
        "gap_cells (пробелы обследования), `covered_cell_counts` [{cx, cy, "
        "observations}] и вклад маршрутов (`routes`).\n"
        "- `cx`/`cy` — индексы ячейки от area_bbox.min_longitude/min_latitude.\n\n"
        "Методика — прозрачная эвристика: ячейка покрыта, если в неё попало ≥1 "
        "геолоцированное наблюдение; это не модель дорожной сети. Наблюдения "
        "маршрутов учитываются только внутри демо-зоны. "
        "См. docs/api/geospatial.md, docs/api/overview.md."
    ),
)
async def coverage(session: SessionDep, settings: SettingsDep, user: CurrentUser) -> dict:
    return await AnalyticsService(session, settings).coverage()
