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
./scripts/bootstrap.sh     # .env, зависимости, db/redis/s3, миграции
make dev                   # API + worker с hot reload (compose dev)
# либо полный стек в контейнерах:
make up                    # сборка образа, миграции, backend + worker
make seed                  # синтетические демо-данные (15 assets, 3 маршрута, reviews)
```

- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json (экспорт: `make openapi`)
- Health: `/health`, `/health/live`, `/health/ready` · Metrics: `/metrics`
- Демо-вход: `admin` / пароль из `.env` (`BOOTSTRAP_ADMIN_PASSWORD`) либо
  `demo-operator` / `demo-operator-password` (создаётся seed-скриптом, только dev).

`.env` создаётся из `.env.example`. **В production `JWT_SECRET_KEY` обязателен** —
без него приложение не стартует. Секреты не коммитятся.

## Основные команды

| Команда | Действие |
|---|---|
| `make up` / `make down` | полный стек в Docker |
| `make dev` | infra в Docker + API/worker с hot reload |
| `make migrate` | `alembic upgrade head` |
| `make seed` | демо-данные |
| `make test` | все тесты (поднимает infra, coverage) |
| `make lint` | ruff check + format check + mypy |
| `make openapi` | экспорт `contracts/openapi/openapi.json` |

## Тесты

262 теста: unit (доменная логика), integration (реальные PostgreSQL/PostGIS, Redis, S3),
API (все endpoints), contract (ML JSON Schema + frontend-контракты).
SQLite не используется. Тестовая БД `mgts_infra_test` создаётся и мигрируется автоматически.

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
| Frontend | [frontend-contract](docs/integrations/frontend-contract.md), [OpenAPI](contracts/openapi/openapi.json) |
| Хранилище | [storage](docs/integrations/storage.md) |
| Эксплуатация | [local-development](docs/operations/local-development.md), [deployment](docs/operations/deployment.md), [troubleshooting](docs/operations/troubleshooting.md) |
| Разработка | [testing](docs/development/testing.md), [новый тип объекта](docs/development/adding-new-asset-type.md), [новый дефект](docs/development/adding-new-defect-type.md), [новый ML-провайдер](docs/development/adding-new-ml-provider.md) |
| Решения | [ADR-0001…0012](docs/decisions/) |
| Безопасность | [SECURITY.md](SECURITY.md), [privacy](docs/security/privacy.md) |
| Для coding agents | [AGENTS.md](AGENTS.md) |
| Исследование | [industry-research](docs/research/industry-research.md) |

## Команды

- **Backend**: этот репозиторий; точки расширения — интерфейсы в `app/application/interfaces/`.
- **ML**: реализуйте 4 endpoint'а по [контракту v1.0](docs/integrations/ml-contract.md),
  подключите через `ML_PROVIDER=http`. Доменные модели менять не нужно.
- **Frontend**: [frontend-contract](docs/integrations/frontend-contract.md) + OpenAPI →
  генерация TypeScript-клиента (`openapi-typescript` / `orval`).

## Лицензия

MIT — см. [LICENSE](LICENSE).
