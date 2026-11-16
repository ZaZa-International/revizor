"""ML integration management endpoints (not a replacement for the ML API)."""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from fastapi import APIRouter

from app.api.route import DocumentedRoute
from app.core.exceptions import MLProviderError
from app.dependencies import CurrentUser, MLDep
from app.schemas.ml import MLHealth, MLModelInfo

router = APIRouter(prefix="/ml", tags=["ML Integration"], route_class=DocumentedRoute)


@router.get(
    "/health",
    response_model=MLHealth,
    summary="Здоровье ML-провайдера",
    description=(
        "Проверка доступности ML-провайдера со стороны backend (mock или http).\n\n"
        "- **200** — MLHealth: `status` (ok/degraded/unavailable), `model_loaded`, "
        "`provider`, `details`. Отказ провайдера не является ошибкой endpoint: "
        "он возвращается как 200 со `status: unavailable` и кодом ошибки в details.\n\n"
        "Backend общается с ML только по контракту v1.0 (contracts/ml/); ошибки "
        "инференса в pipeline маппятся в 502/503/504 единого формата ошибок. "
        "Агрегированное здоровье сервиса — `/health`. "
        "См. docs/integrations/ml-contract.md, docs/api/overview.md."
    ),
)
async def ml_health(ml: MLDep, user: CurrentUser) -> MLHealth:
    try:
        return await ml.health()
    except MLProviderError as exc:
        return MLHealth(
            status="unavailable", model_loaded=False, provider=ml.name, details={"error": exc.code}
        )


@router.get(
    "/model-info",
    response_model=MLModelInfo,
    summary="Имя и версия активной ML-модели",
    description=(
        "Идентификация модели, которую использует провайдер: `name`, `version`, "
        "`schema_version` (версия ML-контракта, сейчас 1.0).\n\n"
        "- **200** — MLModelInfo.\n"
        "- Ошибка провайдера (недоступность/нарушение контракта) → 502/503/504 "
        "единого формата ошибок.\n\n"
        "Используется для отображения версии модели в карточках наблюдений "
        "(model_name/model_version) и диагностики интеграции. "
        "См. docs/integrations/ml-contract.md."
    ),
)
async def ml_model_info(ml: MLDep, user: CurrentUser) -> MLModelInfo:
    return await ml.model_info()
