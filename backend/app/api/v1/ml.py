"""ML integration management endpoints (not a replacement for the ML API)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import MLProviderError
from app.dependencies import CurrentUser, MLDep
from app.schemas.ml import MLHealth, MLModelInfo

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/health", response_model=MLHealth, summary="ML provider health")
async def ml_health(ml: MLDep, user: CurrentUser) -> MLHealth:
    try:
        return await ml.health()
    except MLProviderError as exc:
        return MLHealth(
            status="unavailable", model_loaded=False, provider=ml.name, details={"error": exc.code}
        )


@router.get("/model-info", response_model=MLModelInfo, summary="Active model name/version")
async def ml_model_info(ml: MLDep, user: CurrentUser) -> MLModelInfo:
    return await ml.model_info()
