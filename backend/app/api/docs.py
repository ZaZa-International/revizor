"""Developer Portal: кастомный Swagger UI (/docs) и метаданные тегов OpenAPI.

Используется официальный механизм FastAPI (get_swagger_ui_html): JS/OAuth/
Try-it-out не модифицируются, добавляются только CSS-тема и баннер.
"""
# ruff: noqa: RUF001  # русскоязычная документация API: кириллица и тире намеренны (ложные срабатывания)

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from app.config import get_settings

_GITHUB = "https://github.com/ZaZa-International/revizor"

_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#0B1F3A"/>'
    '<path d="M32 18 L22 52 M32 18 L42 52 M26.5 36 h11 M24 45 h16" '
    'stroke="#38BDF8" stroke-width="3" fill="none" stroke-linecap="round"/>'
    '<circle cx="32" cy="15" r="3.5" fill="#38BDF8"/>'
    '<path d="M22 12 a14 14 0 0 1 20 0 M17 8 a21 21 0 0 1 30 0" '
    'stroke="#38BDF8" stroke-width="2.5" fill="none" stroke-linecap="round" opacity="0.85"/>'
    "</svg>"
)
FAVICON_URL = "data:image/svg+xml," + quote(_LOGO_SVG)

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "System & Health",
        "description": (
            "Служебные пробы жизнеспособности и готовности сервиса: `/health/live`, "
            "`/health/ready`, `/health`. Не требуют аутентификации и используются "
            "оркестраторами, балансировщиками и мониторингом. `/health/ready` и `/health` "
            "проверяют PostgreSQL, Redis и хранилище (критичные компоненты) и возвращают "
            "503 при отказе любого из них; деградация ML даёт статус `degraded` без 503. "
            "Метрики Prometheus доступны на `/metrics` (вне OpenAPI-контракта). "
            "Подробнее: [docs/api/overview.md]("
            f"{_GITHUB}/blob/main/docs/api/overview.md) и [docs/api/errors.md]("
            f"{_GITHUB}/blob/main/docs/api/errors.md)."
        ),
    },
    {
        "name": "Authentication & Users",
        "description": (
            "Аутентификация и профиль пользователя: вход по логину/паролю, отзыв токена "
            "и чтение текущего профиля. API использует JWT Bearer (HS256): "
            "`POST /auth/login` возвращает `access_token` сроком жизни 60 минут "
            "(настраивается), далее все запросы выполняются с заголовком "
            "`Authorization: Bearer <token>`. Роли: ADMIN, OPERATOR, VIEWER, SERVICE; "
            "VIEWER — только чтение без доступа к медиафайлам. `POST /auth/logout` "
            "отзывает текущий токен через denylist (jti). "
            "Быстрый старт и роли: [docs/api/authentication.md]("
            f"{_GITHUB}/blob/main/docs/api/authentication.md); формат ошибок 401/403: "
            f"[docs/api/errors.md]({_GITHUB}/blob/main/docs/api/errors.md)."
        ),
    },
    {
        "name": "Uploads & Media",
        "description": (
            "Загрузка изображений и видео инспекции проездов (drive-by): multipart-ингест, "
            "проверка формата (расширение + MIME + magic bytes), дедупликация по SHA-256. "
            "Ключевые сущности — Upload и StoredFile; GPS-трек передаётся в поле "
            "`metadata` (JSON-строка с `gps_track` и `capture_started_at`). "
            "Новый файл → 201, дубликат по checksum → 200 (`created: false`); чужой "
            "дубликат возвращается в редактированном виде (без имени файла, ключа и GPS). "
            "Это шаги 1–2 сквозного сценария login → upload → job → poll → observations → "
            "asset → review → map → export. "
            "Подробнее: [docs/api/upload-and-processing.md]("
            f"{_GITHUB}/blob/main/docs/api/upload-and-processing.md) и "
            f"[docs/api/workflows.md]({_GITHUB}/blob/main/docs/api/workflows.md)."
        ),
    },
    {
        "name": "Processing Jobs",
        "description": (
            "Асинхронная обработка загрузок в worker (RQ): извлечение кадров, quality "
            "gate, privacy filter, ML-инференс, трекинг, геолокация, дедупликация, "
            "risk scoring и персистенция наблюдений. Жизненный цикл: PENDING → QUEUED → "
            "PROCESSING → COMPLETED / PARTIALLY_COMPLETED / FAILED / CANCELLED; "
            "прогресс опрашивается через `GET /jobs/{id}` каждые 1–2 секунды. "
            "Повторный запуск идемпотентен (обработанные кадры пропускаются), retry "
            "допустим для FAILED/PARTIALLY_COMPLETED/CANCELLED и «зависших» PROCESSING, "
            "а второй активный job одной загрузки отклоняется с 409. "
            "Шаги 2–4 сквозного сценария: [docs/api/upload-and-processing.md]("
            f"{_GITHUB}/blob/main/docs/api/upload-and-processing.md), "
            f"[docs/api/workflows.md]({_GITHUB}/blob/main/docs/api/workflows.md)."
        ),
    },
    {
        "name": "Infrastructure Assets",
        "description": (
            "Реестр физических объектов телеком-инфраструктуры (колодцы, опоры, шкафы, "
            "кабельные линии): карточка Asset с координатами, состоянием, приоритетом "
            "0–100 и полосой приоритета. Приоритет считается внутренней risk-политикой "
            "(факторы сохраняются в `priority_factors`), оператор может задать "
            "`priority_override` с обязательным обоснованием. Ручные обновления "
            "защищены оптимистичной блокировкой (`expected_version` → 409 при конфликте), "
            "история изменений состояния доступна через `/assets/{id}/history`. "
            "Поиск ближайших объектов — `/assets/nearby` (PostGIS geography, метры). "
            "Подробнее: [docs/api/geospatial.md]("
            f"{_GITHUB}/blob/main/docs/api/geospatial.md), "
            f"[docs/api/workflows.md]({_GITHUB}/blob/main/docs/api/workflows.md)."
        ),
    },
    {
        "name": "Observations",
        "description": (
            "Наблюдения — отдельные ML-детекции объектов на кадрах, привязанные к job и "
            "(после дедупликации) к asset. Исходное предсказание хранится в "
            "`object_type/condition_class/severity/detector_confidence`, человеческое "
            "решение — в `effective_*` и `review_status`; исходные предсказания никогда "
            "не затираются. Очередь проверки оператора: "
            "`GET /observations?review_status=UNREVIEWED` (+`dedup_result=POSSIBLE_MATCH` "
            "для неразрешённых совпадений). Медиа-ссылки (`image_url`, `crop_url`) "
            "доступны только ролям OPERATOR/SERVICE/ADMIN — VIEWER получает их как null. "
            "Шаги 5–6 сценария: [docs/api/workflows.md]("
            f"{_GITHUB}/blob/main/docs/api/workflows.md), "
            f"[docs/api/upload-and-processing.md]({_GITHUB}/blob/main/docs/api/upload-and-processing.md)."
        ),
    },
    {
        "name": "Defects & Risk",
        "description": (
            "Реестр дефектов физических объектов: тип, severity 1–5, статус и счётчик "
            "подтверждающих наблюдений. Дефекты создаются pipeline из детекций и "
            "обновляются оператором через PATCH с явной матрицей переходов: "
            "OPEN → CONFIRMED/IN_PROGRESS/RESOLVED/REJECTED; CONFIRMED → "
            "IN_PROGRESS/RESOLVED; IN_PROGRESS → CONFIRMED/RESOLVED; RESOLVED → OPEN "
            "(reopen); REJECTED терминален через API. Приоритет объекта объединяет "
            "severity, уверенность и тип объекта по внутренней risk-политике "
            "(`priority_factors`, `priority_policy_version`). "
            "Подробнее: [docs/api/workflows.md]("
            f"{_GITHUB}/blob/main/docs/api/workflows.md) и [docs/api/overview.md]("
            f"{_GITHUB}/blob/main/docs/api/overview.md)."
        ),
    },
    {
        "name": "Reviews & Human-in-the-loop",
        "description": (
            "Операторская проверка ML-предсказаний: append-only журнал решений "
            "CONFIRMED / REJECTED / CORRECTED / NEEDS_MORE_INFORMATION по observation "
            "или defect. Исправления (`corrected_asset_type`, `corrected_condition`, "
            "`corrected_defect_type`, `corrected_severity`) допустимы только при "
            "CORRECTED и минимум одно обязательно; condition проверяется по словарю "
            "(ok, damaged, damaged_cover, missing_cover, door_open, tilted, subsided, "
            "cable_sag, cable_break, unknown и алиасы). Review применяет изменения к "
            "наблюдению/дефекту/активу, пересчитывает приоритет и создаёт training "
            "examples; повторная проверка создаёт новую запись, история не перезаписывается. "
            "Шаг 7 сценария: [docs/api/workflows.md]("
            f"{_GITHUB}/blob/main/docs/api/workflows.md), "
            f"[docs/api/errors.md]({_GITHUB}/blob/main/docs/api/errors.md)."
        ),
    },
    {
        "name": "Geospatial & Maps",
        "description": (
            "GeoJSON-слои (RFC 7946) для MapLibre и любого GIS-frontend: активы, "
            "дефекты, наблюдения и треки маршрутов. Координаты строго "
            "`[longitude, latitude]` (WGS84); bbox-фильтр — "
            "`min_lon,min_lat,max_lon,max_lat`. Объекты без GPS "
            "(`geolocation_status=UNAVAILABLE`) в слои не попадают — показывайте их в "
            "списочном представлении. Слои типизированы (FeatureCollection со схемами "
            "properties, специфичными для слоя) и ограничены `limit` для производительности. "
            "Шаг 8 сценария: [docs/api/geospatial.md]("
            f"{_GITHUB}/blob/main/docs/api/geospatial.md), "
            f"[docs/api/workflows.md]({_GITHUB}/blob/main/docs/api/workflows.md)."
        ),
    },
    {
        "name": "Routes & Inspections",
        "description": (
            "Маршруты объезда (survey routes): имя, транспорт, время начала/окончания "
            "и GPS-трек. Трек передаётся парами `[longitude, latitude]` (2–10000 точек), "
            "хранится как PostGIS LINESTRING; `total_distance_m` вычисляется в метрах "
            "через ST_Length. Маршрут связывает загрузки и jobs с физическим объездом "
            "и используется дедупликацией (same-route фактор) и аналитикой покрытия. "
            "Создание идемпотентно через `Idempotency-Key`. "
            "Подробнее: [docs/api/geospatial.md]("
            f"{_GITHUB}/blob/main/docs/api/geospatial.md) и "
            f"[docs/api/upload-and-processing.md]({_GITHUB}/blob/main/docs/api/upload-and-processing.md)."
        ),
    },
    {
        "name": "Analytics & Coverage",
        "description": (
            "Агрегированная аналитика для дашбордов: счётчики сущностей, распределения "
            "активов по типам и полосам приоритета, дефектов по статусам и severity, "
            "job'ов по статусам, доля проверенных наблюдений. `/analytics/coverage` "
            "строит сетку покрытия демо-зоны (ячейки ~250 м): covered/gap cells, "
            "coverage_ratio и вклад каждого маршрута. Все ответы типизированы и "
            "предназначены для прямого рендеринга графиками. "
            "Подробнее: [docs/api/overview.md]("
            f"{_GITHUB}/blob/main/docs/api/overview.md) и [docs/api/geospatial.md]("
            f"{_GITHUB}/blob/main/docs/api/geospatial.md)."
        ),
    },
    {
        "name": "Exports & Reports",
        "description": (
            "Выгрузки реестров в CSV (UTF-8 с BOM, Excel-friendly) и XLSX: активы, "
            "наблюдения, дефекты. Фильтры полностью совпадают со списочными endpoints "
            "(передавайте фильтры UI один в один), сортировка детерминирована. "
            "Лимит выгрузки — 50 000 строк; при усечении ответ несёт заголовок "
            "`X-Export-Truncated: true`, файл отдаётся как attachment "
            "(`Content-Disposition`). Каждая выгрузка фиксируется в audit log. "
            "Шаг 9 сценария: [docs/api/pagination-filtering.md]("
            f"{_GITHUB}/blob/main/docs/api/pagination-filtering.md), "
            f"[docs/api/workflows.md]({_GITHUB}/blob/main/docs/api/workflows.md)."
        ),
    },
    {
        "name": "ML Integration",
        "description": (
            "Управление ML-интеграцией со стороны backend: здоровье провайдера и "
            "информация об активной модели. Backend общается с ML-сервисом только по "
            "контракту v1.0 (JSON Schema в `contracts/ml/`), не зная внутренних "
            "фреймворков; провайдеры — mock (dev/test) и http (production). "
            "Эти endpoints НЕ заменяют ML API инференса — детекции приходят в API "
            "через processing pipeline. Ошибки провайдера маппятся в 502/503/504 "
            "единого формата ошибок. "
            "Подробнее: [docs/integrations/ml-contract.md]("
            f"{_GITHUB}/blob/main/docs/integrations/ml-contract.md) и "
            f"[docs/api/overview.md]({_GITHUB}/blob/main/docs/api/overview.md)."
        ),
    },
    {
        "name": "Storage & Files",
        "description": (
            "Аутентифицированное скачивание файлов хранилища по storage key — "
            "используется при local storage backend. При S3-бэкенде frontend работает "
            "напрямую с presigned URL (`presigned_url`, `image_url`, `crop_url`), срок "
            "жизни которых ограничен (по умолчанию 3600 с). Доступ к медиа разрешён "
            "только OPERATOR/SERVICE/ADMIN: VIEWER получает 403, что согласовано с "
            "отсутствием медиа-ссылок в его ответах observations/uploads. "
            "Подробнее: [docs/api/upload-and-processing.md]("
            f"{_GITHUB}/blob/main/docs/api/upload-and-processing.md) и "
            f"[docs/api/authentication.md]({_GITHUB}/blob/main/docs/api/authentication.md)."
        ),
    },
]

_SWAGGER_UI_PARAMETERS = {
    "persistAuthorization": True,
    "deepLinking": True,
    "tryItOutEnabled": True,
    "displayRequestDuration": True,
    "filter": True,
    "docExpansion": "list",
    "defaultModelsExpandDepth": 1,
    "syntaxHighlight": {"theme": "agate"},
}


def _banner_html(version: str, environment: str) -> str:
    env_class = f"mgts-env mgts-env--{environment}"
    return (
        '<div class="mgts-banner">'
        '<div class="mgts-banner__brand">'
        '<img class="mgts-banner__logo" src="/static/logo.svg" alt="MGTS logo">'
        '<span class="mgts-banner__wordmark">MGTS Infrastructure Intelligence</span>'
        f'<span class="mgts-badge mgts-badge--version">API v{version}</span>'
        f'<span class="{env_class}">{environment}</span>'
        "</div>"
        '<nav class="mgts-banner__links">'
        f'<a href="{_GITHUB}#readme" target="_blank" rel="noopener">README</a>'
        f'<a href="{_GITHUB}/tree/main/docs/architecture" target="_blank" rel="noopener">'
        "Архитектура</a>"
        f'<a href="{_GITHUB}/blob/main/docs/api/overview.md" target="_blank" rel="noopener">'
        "API Overview</a>"
        f'<a href="{_GITHUB}" target="_blank" rel="noopener">GitHub</a>'
        "</nav>"
        "</div>"
    )


router = APIRouter(include_in_schema=False)


@router.get("/docs", response_class=HTMLResponse)
async def swagger_ui(request: Request) -> HTMLResponse:
    settings = get_settings()
    response = get_swagger_ui_html(
        openapi_url=request.app.openapi_url,
        title="MGTS Infrastructure Intelligence — Developer Portal",
        swagger_favicon_url=FAVICON_URL,
        swagger_ui_parameters=_SWAGGER_UI_PARAMETERS,
    )
    html = bytes(response.body).decode("utf-8")
    html = html.replace("</head>", '<link rel="stylesheet" href="/static/swagger.css">\n</head>', 1)
    html = html.replace(
        "<body>", "<body>\n" + _banner_html(settings.app_version, settings.app_env), 1
    )
    return HTMLResponse(content=html)
