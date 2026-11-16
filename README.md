# MGTS Infrastructure Intelligence (`mgts-infra`)

Backend-платформа интеллектуального мониторинга телекоммуникационной инфраструктуры МГТС
по изображениям и видео с камер служебных автомобилей: цифровой реестр объектов,
оценка состояния, геопривязка, дедупликация повторных обнаружений, приоритизация рисков,
проверка оператором (human-in-the-loop) и накопление проверенных данных для обучения моделей.

> Статус: MVP хакатона (72 часа). Все данные в демо-режиме синтетические.
> ML-модель подключается через стабильный контракт; в MVP работает Mock ML Provider.

## Архитектура

Модульный монолит, 4 слоя: **API → Application → Domain ← Infrastructure**.
Домен не зависит от FastAPI/SQLAlchemy/ML-фреймворков. ML inference — внешний компонент
за интерфейсом `MLProvider`. Тяжёлая обработка видео — в RQ worker, не в HTTP-запросе.

```
backend/app/
├── api/v1/          # тонкие роутеры, Pydantic-схемы отдельно от ORM
├── application/     # сервисы, use cases (pipeline), интерфейсы (порты)
├── domain/          # enums, таксономии, чистая логика: dedup/risk/review/geolocation
├── infrastructure/  # SQLAlchemy+PostGIS, репозитории, S3/local storage, ML, RQ
├── workers/         # RQ worker entrypoint + задачи
└── core/            # security, logging, metrics, middleware, exceptions
```

Подробно: [docs/architecture/system-overview.md](docs/architecture/system-overview.md),
[диаграммы](docs/architecture/component-diagram.md), [ADR](docs/decisions/).

## Стек

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 async + asyncpg · GeoAlchemy2 ·
PostgreSQL 16 + PostGIS 3.4 · Alembic · Redis 7 + RQ 3 · S3 (SeaweedFS в dev; MinIO-совместимо,
см. [ADR-0006](docs/decisions/ADR-0006-s3-abstraction-seaweedfs.md)) · OpenCV (headless) ·
structlog · Prometheus · OpenTelemetry (опционально) · Argon2id + JWT · pytest · Ruff · mypy · uv.

## Быстрый старт

Требования: Docker + Compose v2, [uv](https://docs.astral.sh/uv/), Python 3.12 (uv поставит сам).

```bash
./scripts/bootstrap.sh     # .env, зависимости, infra (dev-override), миграции
make dev                   # API + worker с hot reload (compose dev)
# либо полный стек в контейнерах:
make up                    # сборка образа, one-shot migrate, backend + worker
make seed                  # синтетические демо-данные (15 assets, 3 маршрута, reviews)
```

> Безопасность по умолчанию: базовый compose **не публикует** порты PostgreSQL/Redis/S3
> на хост (только API 8000). Локальная разработка с хоста использует dev-override
> (`make dev`, bootstrap/test.sh подключают его автоматически).

- **Developer Portal (Swagger UI)**: http://localhost:8000/docs — фирменный интерфейс,
  14 разделов, примеры, Try it out с persistAuthorization.
- OpenAPI JSON: http://localhost:8000/openapi.json (экспорт: `make openapi`,
  drift-check: `make openapi-check`, breaking: `make breaking-check`,
  TypeScript-клиент: `make ts-client`)
- Health: `/health`, `/health/live`, `/health/ready` · Metrics API: `/metrics` ·
  Metrics worker: `:9100/metrics` (dev-override)
- Демо-вход: `admin` / пароль из `.env` (`BOOTSTRAP_ADMIN_PASSWORD`) либо
  `demo-operator` / `demo-operator-password` (создаётся seed-скриптом, только dev).
- Logout: `POST /api/v1/auth/logout` (отзыв токена через jti denylist).

`.env` создаётся из `.env.example` (секреты пустые). **В production валидатор отклоняет
placeholder-секреты**: `JWT_SECRET_KEY` ≥32 символов, S3-credentials не `minioadmin`,
`QUEUE_MODE` не `inline`, CORS без `*`. Секреты не коммитятся.

## Основные команды

| Команда | Действие |
|---|---|
| `make up` / `make down` | полный стек в Docker (infra без host-портов) |
| `make dev` | infra с портами + API/worker с hot reload |
| `make migrate` | `alembic upgrade head` |
| `make seed` | демо-данные |
| `make test` | все тесты (поднимает infra, coverage) |
| `make lint` | ruff check + format check + mypy |
| `make openapi` / `openapi-check` | экспорт / drift-check OpenAPI |
| `make ts-client` / `breaking-check` | TypeScript-клиент / oasdiff breaking |
| `bash scripts/ci_local.sh` | полный локальный CI (12 шагов) |
| `bash scripts/smoke.sh` | end-to-end smoke против стека |
| `bash scripts/backup.sh` / `restore.sh` | backup/restore PostgreSQL + S3 |

## Тесты

**661 тест**: unit (доменная логика, автономны), integration (реальные PostgreSQL/PostGIS,
Redis, S3), API (все endpoints + security regression + role matrix), contract
(ML JSON Schema + OpenAPI + frontend-контракты), concurrency/failure-modes.
SQLite не используется. Тестовая БД `mgts_infra_test` создаётся и мигрируется автоматически;
`TEST_DB_NAME` — изоляция параллельных прогонов.

```bash
cd backend
uv run pytest -m unit          # без внешних сервисов
uv run pytest                  # всё (нужны db/redis/s3 из compose)
```

Подробнее: [docs/development/testing.md](docs/development/testing.md).

## API workflows

1. **Upload → Processing**: `POST /api/v1/uploads` (multipart, GPS-трек в `metadata`) →
   `POST /api/v1/jobs` → worker извлекает кадры, quality gate, mock/HTTP inference,
   дедупликация, risk scoring → `GET /api/v1/jobs/{id}` (прогресс, статусы).
2. **Реестр и карта**: `GET /api/v1/assets` (фильтры, bbox, пагинация),
   `GET /api/v1/map/assets` (GeoJSON для MapLibre), история `/assets/{id}/history`.
3. **Review**: `POST /api/v1/reviews` (CONFIRMED/REJECTED/CORRECTED/NEEDS_MORE_INFORMATION) —
   append-only; исправления не затирают исходный ML-результат; проверенные примеры
   накапливаются в `training_examples`.
4. **Экспорт**: `GET /api/v1/exports/{assets|defects|observations}?format=csv|xlsx` с фильтрами.
5. **Аналитика**: `/analytics/overview`, `/analytics/defects`, `/analytics/coverage`.

## Документация

| Раздел | Файлы |
|---|---|
| Архитектура | [system-overview](docs/architecture/system-overview.md), [data-flow](docs/architecture/data-flow.md), [domain-model](docs/architecture/domain-model.md), [диаграммы](docs/architecture/sequence-diagrams.md) |
| База данных | [schema](docs/database/schema.md), [geospatial](docs/database/geospatial.md) |
| ML-интеграция | [ml-contract](docs/integrations/ml-contract.md), [примеры](docs/integrations/ml-examples/), [JSON Schema](contracts/ml/) |
| API (Developer Portal) | [overview](docs/api/overview.md), [authentication](docs/api/authentication.md), [errors](docs/api/errors.md), [pagination/filtering](docs/api/pagination-filtering.md), [geospatial](docs/api/geospatial.md), [upload & processing](docs/api/upload-and-processing.md), [workflows](docs/api/workflows.md) |
| Frontend | [integrations README](docs/integrations/README.md), [frontend-contract](docs/integrations/frontend-contract.md), [OpenAPI](contracts/openapi/openapi.json), [TypeScript](contracts/typescript/) |
| Хранилище | [storage](docs/integrations/storage.md) |
| Эксплуатация | [local-development](docs/operations/local-development.md), [deployment](docs/operations/deployment.md), [troubleshooting](docs/operations/troubleshooting.md) |
| Разработка | [testing](docs/development/testing.md), [новый тип объекта](docs/development/adding-new-asset-type.md), [новый дефект](docs/development/adding-new-defect-type.md), [новый ML-провайдер](docs/development/adding-new-ml-provider.md) |
| Решения | [ADR-0001…0012](docs/decisions/) |
| Аудит | [backend-audit](docs/audit/backend-audit.md) (регистр находок + статусы исправлений) |
| Безопасность | [SECURITY.md](SECURITY.md), [privacy](docs/security/privacy.md) |
| Для coding agents | [AGENTS.md](AGENTS.md) |
| Исследование | [industry-research](docs/research/industry-research.md) |

## Команды

- **Backend**: этот репозиторий; точки расширения — интерфейсы в `app/application/interfaces/`.
- **ML**: реализуйте 4 endpoint'а по [контракту v1.0](docs/integrations/ml-contract.md),
  подключите через `ML_PROVIDER=http`. Доменные модели менять не нужно.
- **Frontend**: [integrations README](docs/integrations/README.md) + OpenAPI →
  `make ts-client` (openapi-typescript + openapi-fetch); drift/breaking контролируются
  `make openapi-check` / `make breaking-check` и CI.

## Лицензия

MIT — см. [LICENSE](LICENSE).
