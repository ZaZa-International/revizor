# API Overview — MGTS Infrastructure Intelligence

Backend мониторинга телеком-инфраструктуры МГТС: съёмка с автомобиля →
загрузка изображений/видео → покадровая обработка и ML-детекции → дедупликация
физических объектов → реестр активов и дефектов → risk scoring → проверка
оператором → карта, аналитика и экспорт.

Этот раздел — справочник разработчика интеграций (developer portal).
Машиночитаемый источник истины — OpenAPI-контракт
[`contracts/openapi/openapi.json`](../../contracts/openapi/openapi.json);
интерактивная документация доступна на запущенном сервере: **Swagger UI `/docs`**,
**ReDoc `/redoc`**, сырая схема `/openapi.json`.

## Base URL и версия

| Окружение | Base URL | Префикс API |
|---|---|---|
| Dev (compose) | `http://localhost:8000` | `/api/v1` |
| Production | задаётся deployment-конфигурацией | `/api/v1` |

Все эндпоинты, кроме `POST /api/v1/auth/login` и health-проб (`/health`,
`/health/live`, `/health/ready`), требуют Bearer-токен
([authentication.md](authentication.md)). `/metrics` (Prometheus) — без auth,
предназначен для внутренней сети.

## Модель сущностей

| Сущность | Что это | Ключевые endpoint'ы |
|---|---|---|
| **Upload** | Загруженный оригинал (фото/видео) с checksum-дедупликацией и GPS-метаданными | `/api/v1/uploads` |
| **Route** | Маршрут объезда: трек `[lon, lat]`, длина считается PostGIS | `/api/v1/routes` |
| **Job** | Задача обработки загрузки: кадры → ML → нормализация → гео → дедупликация → risk → персистенция | `/api/v1/jobs` |
| **Observation** | Единичное ML-наблюдение объекта на кадре (bbox, confidence, состояние) + результат дедупликации и статус проверки | `/api/v1/observations` |
| **Asset** | Физический объект инфраструктуры (колодец, опора, шкаф, кабельная линия): текущее состояние, приоритет 0…100, версия для оптимистичной блокировки | `/api/v1/assets` |
| **Defect** | Дефект актива (отсутствующая крышка, наклон опоры…): severity 1…5, статусная модель | `/api/v1/defects` |
| **Review** | Append-only решение оператора по наблюдению/дефекту (CONFIRMED/REJECTED/CORRECTED/NEEDS_MORE_INFORMATION) | `/api/v1/reviews` |

Связи: `Upload → Job → Observation → Asset → Defect`; `Review` ссылается на
Observation или Defect и изменяет их эффективные значения; история изменений
состояния актива — `/api/v1/assets/{id}/history`.

Типы объектов и дефектов — открытые реестры домена (новые коды не требуют
миграции БД): `telecom_well`, `pole`, `telecom_cabinet`, `cable_line`, `other`;
канонические состояния — `ok`, `damaged`, `damaged_cover`, `missing_cover`,
`door_open`, `tilted`, `subsided`, `cable_sag`, `cable_break`, `unknown`.

## Политика версионирования

- **API v1, проект pre-1.0.** Ломающие изменения контракта допускаются, но
  обязательно сопровождаются: записью в [CHANGELOG](../../CHANGELOG.md),
  обновлением этой документации и OpenAPI, контрактными тестами
  (`backend/tests/contracts/`). Примеры breaking-изменений 0.2.0: пагинация
  кадров/истории, gating медиа для VIEWER, 422 на неизвестный `sort_by`.
- **После 1.0** ломающие изменения — только через новый префикс `/api/v2`;
  v1 поддерживается параллельно в течение объявленного переходного периода.
- **ML-контракт версионируется отдельно** (`schema_version`, сейчас `"1.0"`):
  аддитивные изменения — без смены версии, ломающие — новый `schema_version`
  и префикс `/v2` на стороне ML-сервиса. См.
  [ml-contract.md](../integrations/ml-contract.md).
- Аддитивные изменения API (новые опциональные поля/эндпоинты) — минорные:
  клиенты должны игнорировать незнакомые поля.

## Quickstart (5 команд)

```bash
# 1. Инфраструктура: PostgreSQL/PostGIS, Redis, S3 (SeaweedFS) + бакет
docker compose up -d db redis s3 s3-init

# 2. Зависимости backend (Python 3.12, uv)
cd backend && uv sync

# 3. Миграции
uv run alembic upgrade head

# 4. API с hot reload (admin создаётся при BOOTSTRAP_ADMIN_PASSWORD в .env)
uv run uvicorn app.main:app --reload --port 8000

# 5. Логин и первый запрос
curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<ваш BOOTSTRAP_ADMIN_PASSWORD>"}'
```

Полный стек (API + worker) одной командой: `make dev`. Подробности окружения —
[local-development.md](../operations/local-development.md).

## Инструменты контракта

| Команда | Назначение |
|---|---|
| `make openapi` | Экспорт `app.openapi()` в `contracts/openapi/openapi.json` |
| `make openapi-check` | Drift-проверка: committed-контракт == live-схема (exit 1 при расхождении) |
| `make breaking-check` | Breaking-изменения относительно `origin/main` (tufin/oasdiff, нужен docker) |
| `make ts-client` | Генерация `contracts/typescript/schema.d.ts` (openapi-typescript) |
| `cd backend && uv run pytest tests/contracts -m contract` | Контрактные тесты (ML + frontend + OpenAPI) |

Готовые примеры ответов каждого endpoint'а —
[`contracts/examples/api/`](../../contracts/examples/api/) (валидируются
контрактными тестами против компонентных схем OpenAPI).

## Разделы справочника

1. [Аутентификация и роли](authentication.md)
2. [Ошибки](errors.md)
3. [Пагинация, сортировка, фильтры](pagination-filtering.md)
4. [Геопространственные данные](geospatial.md)
5. [Загрузка и обработка](upload-and-processing.md)
6. [Сквозные сценарии (curl)](workflows.md)

Смежные документы: [frontend-contract.md](../integrations/frontend-contract.md),
[ml-contract.md](../integrations/ml-contract.md), [storage.md](../integrations/storage.md),
[privacy.md](../security/privacy.md), [integrations README](../integrations/README.md).
