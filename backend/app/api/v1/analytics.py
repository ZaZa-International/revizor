from __future__ import annotations

from fastapi import APIRouter

from app.application.services.analytics import AnalyticsService
from app.dependencies import CurrentUser, SessionDep, SettingsDep

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", summary="System-wide counters and distributions")
async def overview(session: SessionDep, settings: SettingsDep, user: CurrentUser) -> dict:
    return await AnalyticsService(session, settings).overview()


@router.get("/defects", summary="Defect aggregation by type")
async def defects_analytics(session: SessionDep, settings: SettingsDep, user: CurrentUser) -> dict:
    return await AnalyticsService(session, settings).defects_analytics()


@router.get("/coverage", summary="Grid-based survey coverage and gaps")
async def coverage(session: SessionDep, settings: SettingsDep, user: CurrentUser) -> dict:
    return await AnalyticsService(session, settings).coverage()
