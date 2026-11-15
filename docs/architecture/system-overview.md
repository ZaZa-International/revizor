# Обзор системы — MGTS Infrastructure Intelligence

> Документ описывает **фактически реализованный** backend (262 теста проходят).
> Все ссылки на код приведены относительно корня репозитория.

## 1. Назначение

MGTS Infrastructure Intelligence — система **drive-by инспекции телеком-инфраструктуры**
(проездная съёмка с автомобиля): кабельные колодцы, опоры, телекоммуникационные шкафы,
кабельные линии. Оператор загружает фото/видео маршрута, система извлекает кадры,
прогоняет их через ML-детектор, нормализует результаты, привязывает к GPS-треку,
дедуплицирует объекты в единый реестр активов, оценивает риск и приоритет,
и предоставляет оператору интерфейс подтверждения/корректировки (human-in-the-loop).

Целевой контекст — хакатон МГТС: демонстрационный, но инженерно честный MVP.
Система **не выдумывает** данные: без GPS координаты отсутствуют (`UNAVAILABLE`),
без анонимизации статус честно `NOT_APPLIED`, неоднозначная дедупликация
**никогда** не сливается автоматически.

## 2. Архитектурный стиль: модульный монолит, 4 слоя

Backend — единый процесс FastAPI (`backend/app/main.py`) плюс отдельный RQ-воркер
(`backend/app/workers/worker.py`), использующий тот же код. Логически код разделён
на четыре слоя с однонаправленными зависимостями (сверху вниз):

```
API  →  Application  →  Domain
                ↘        ↗
              Infrastructure
```

| Слой | Каталоги | Ответственность |
|------|----------|-----------------|
| **API** | `backend/app/api/`, `backend/app/schemas/`, `backend/app/dependencies.py`, `backend/app/main.py` | HTTP-роутеры, Pydantic-схемы запросов/ответов, DI, аутентификация/RBAC, сериализация ORM→DTO |
| **Application** | `backend/app/application/services/`, `backend/app/application/use_cases/processing/`, `backend/app/application/interfaces/` | Оркестрация сценариев, сервисы, pipeline обработки, Protocols-интерфейсы внешних зависимостей |
| **Domain** | `backend/app/domain/` | Чистая бизнес-логика: enums, таксономии, политика дедупликации, risk scoring, state machine, логика review, гео value-objects, нормализация condition |
| **Infrastructure** | `backend/app/infrastructure/`, `backend/app/workers/`, `backend/app/core/`, `backend/app/config.py` | SQLAlchemy-модели и репозитории, ML-провайдеры, очередь, хранилище, воркер, сквозная инфраструктура (security, logging, metrics, middleware) |

### Правила зависимостей (соблюдаются в коде)

1. **Domain имеет нулевые I/O-зависимости.** Модули `backend/app/domain/*` импортируют
   только стандартную библиотеку и соседние модули `app.domain` (enums, таксономии,
   condition). Никакого FastAPI, SQLAlchemy,
   ML-фреймворков, сети или БД. Примеры: `domain/deduplication/policy.py`,
   `domain/risk/scoring.py`, `domain/processing/state_machine.py`, `domain/reviews/logic.py`.
2. **Роутеры тонкие.** `backend/app/api/v1/*.py` разбирают запрос, вызывают сервис/репозиторий
   и сериализуют ответ; бизнес-логика в роутерах отсутствует.
3. **ORM никогда не отдаётся как API-схема.** Ответы строятся через Pydantic-схемы
   (`backend/app/schemas/*`) и конвертеры `backend/app/api/v1/serializers.py`
   (`asset_response`, `observation_response`, `route_response`), которые обогащают
   DTO координатами lon/lat и presigned-URL. Гео-поля ORM (`WKTElement`) наружу не попадают.
4. **Application зависит от интерфейсов, а не реализаций.** `application/interfaces/`
   объявляет `MLProvider`, `ObjectStorage`, `JobQueue` как `typing.Protocol`;
   infrastructure предоставляет реализации и фабрики (`infrastructure/*/factory.py`).
5. **Domain не знает об Infrastructure.** Политика дедупликации получает «свидетельства»
   (`CandidateEvidence`) от application-сервиса, который сам ходит в PostGIS.

## 3. Технологический стек

Версии — из `backend/pyproject.toml` (диапазоны), образы — из `docker-compose.yml`.

| Компонент | Технология | Версия / ограничение |
|-----------|-----------|----------------------|
| Язык | Python | `>=3.12,<3.14` |
| Web-фреймворк | FastAPI | `>=0.163,<0.164` |
| ASGI-сервер | uvicorn[standard] | `>=0.54,<0.55` |
| Валидация/DTO | pydantic | `>=2.14,<3` |
| Конфигурация | pydantic-settings | `>=2.16,<3` |
| ORM (async) | SQLAlchemy[asyncio] | `>=2.1,<2.2` |
| Драйвер БД | asyncpg | `>=0.32,<0.33` |
| Гео-ORM | GeoAlchemy2 | `>=0.21,<0.22` |
| Миграции | Alembic | `>=1.20,<2` |
| Клиент Redis | redis | `>=8.1,<9` |
| Очередь задач | RQ | `>=3.0,<4` |
| S3-клиент | boto3 | `>=1.44,<2` |
| Структурные логи | structlog | `>=26.1,<27` |
| Метрики | prometheus-client | `>=0.26,<0.27` |
| Обработка кадров | opencv-python-headless | `>=5.0,<5.1` |
| XLSX-экспорт | openpyxl | `>=3.1,<4` |
| Хеширование паролей | argon2-cffi (Argon2id) | `>=25.1,<26` |
| JWT | pyjwt | `>=2.15,<3` |
| Multipart | python-multipart | `>=0.0.33,<0.1` |
| HTTP-клиент (ML) | httpx | `>=0.28,<0.29` |
| Гео-геометрия | shapely | `>=2.0,<3` |
| Трейсинг | opentelemetry-api/sdk/exporter-otlp | `>=1.30,<2` (instrumentation `>=0.60b0`) |
| СУБД | PostgreSQL + PostGIS | образ `postgis/postgis:16-3.4` (PG 16, PostGIS 3.4) |
| Кэш/очередь | Redis | образ `redis:7-alpine` |
| Объектное хранилище | SeaweedFS (S3 API) | образ `chrislusf/seaweedfs:latest` |
| Тесты | pytest / pytest-asyncio / pytest-cov | `>=9.2,<10` / `>=1.5,<2` / `>=7.1,<8` |
| Линт/типы | ruff / mypy | `>=0.17,<0.18` / `>=2.4,<3` |

> **Почему SeaweedFS, а не MinIO.** Community-дистрибуция MinIO прекращена
> (репозиторий Docker Hub удалён, `dl.min.io` возвращает 410), поэтому dev/demo
> использует SeaweedFS за тем же S3 API. Решение фиксируется в ADR-0006
> (готовится отдельным агентом). Код хранилища (`infrastructure/storage/s3.py`)
> S3-совместим и не привязан к конкретному серверу.

## 4. Карта модулей

### API (`backend/app/api/`)
- `v1/router.py` — агрегатор роутеров под префиксом `/api/v1`.
- `v1/auth.py` — `POST /auth/login` (JWT, rate limit), `GET /auth/me`.
- `v1/uploads.py` — загрузка multipart, список/получение/удаление upload.
- `v1/jobs.py` — создание job, статус/прогресс, кадры, retry, cancel.
- `v1/assets.py` — реестр активов, nearby (PostGIS), PATCH (optimistic locking), история, наблюдения/дефекты актива.
- `v1/observations.py` — список/получение наблюдений с фильтрами и bbox.
- `v1/defects.py` — список/получение/PATCH дефектов.
- `v1/reviews.py` — append-only review оператора.
- `v1/map.py` — GeoJSON-слои: assets, defects, observations, routes.
- `v1/routes.py` — маршруты съёмки, трек LINESTRING, `ST_Length`.
- `v1/analytics.py` — overview, defects, coverage.
- `v1/exports.py` — CSV/XLSX экспорт assets/observations/defects.
- `v1/ml.py` — health/model-info ML-провайдера.
- `v1/files.py` — авторизованная выдача файлов (local storage).
- `v1/idempotency.py` — helper `idempotent_post` (replay по `Idempotency-Key`).
- `v1/serializers.py` — ORM→DTO конвертеры.
- `errors.py` — единый envelope ошибок `{"error": {code, message, details, request_id}}`.
- `health.py` — `/health/live`, `/health/ready`, `/health`.

### Application (`backend/app/application/`)
- `services/uploads.py` — валидация, checksum-дедуп, хранение, метаданные.
- `services/jobs.py` — жизненный цикл job (create/enqueue/retry/cancel).
- `services/assets.py` — чтение, ручной PATCH, история.
- `services/deduplication.py` — PostGIS-кандидаты + доменная политика; `EmbeddingSimilarityProvider` (заглушка).
- `services/geolocation.py` — GPS-трек → `GeoObservation` (CONFIRMED/ESTIMATED/UNAVAILABLE).
- `services/geospatial.py` — GeoJSON-слои и nearest-поиск.
- `services/history.py` — история состояния и change detection (`is_physical_change`).
- `services/risk.py` — обёртка версионированной risk-политики.
- `services/reviews.py` — human-in-the-loop, training examples.
- `services/analytics.py` — счётчики, агрегация дефектов, grid coverage.
- `services/exports.py` — CSV/XLSX рендеринг.
- `services/idempotency.py` — кэш ответов по ключу.
- `services/auth.py` — login, bootstrap admin.
- `use_cases/processing/pipeline.py` — оркестратор обработки.
- `use_cases/processing/frames.py` — извлечение кадров (OpenCV).
- `use_cases/processing/quality.py` — `QualityGate` / `HeuristicQualityGate`.
- `use_cases/processing/privacy.py` — `PrivacyFilter` / `NoopPrivacyFilter`.
- `interfaces/{ml_provider,storage,queue}.py` — Protocols.

### Domain (`backend/app/domain/`)
- `enums.py` — все доменные перечисления (чистый Python `StrEnum`).
- `assets/taxonomy.py` — реестр типов активов (impact_factor, dedup_radius_m).
- `defects/taxonomy.py` — реестр типов дефектов (default_severity, applicable_asset_types).
- `deduplication/policy.py` — взвешенная политика `weighted-v1`.
- `risk/scoring.py` — формула приоритета и bands.
- `processing/state_machine.py` — переходы статусов job.
- `reviews/logic.py` — валидация и применение review.
- `observations/condition.py` — нормализация condition, default severity, map в defect.
- `geospatial/models.py` — `GeoPoint`, `GeoObservation`, `BoundingBox`, `PixelBBox`, валидация координат.

### Infrastructure (`backend/app/infrastructure/`)
- `database/base.py` — `Base`, naming convention, mixins (UUID PK, created_at/updated_at).
- `database/session.py` — async engine / session factory.
- `database/models/*.py` — 14 ORM-сущностей + ассоциативная таблица.
- `database/repositories/*.py` — репозитории, фильтры, пагинация, гео-запросы.
- `ml/{mock_provider,http_provider,factory}.py` — ML-провайдеры.
- `queue/{rq_queue,inline_queue,factory}.py` — очередь.
- `storage/{s3,local,factory}.py` — объектное хранилище.

### Workers / Core
- `workers/worker.py` — RQ-воркер (`python -m app.workers.worker`).
- `workers/tasks/processing.py` — sync-обёртка задачи, изолированный event loop на выполнение.
- `core/security.py` — Argon2id, JWT.
- `core/{logging,metrics,middleware,observability,ratelimit,exceptions}.py` — сквозные функции.
- `config.py` — `Settings` (pydantic-settings, `.env`).

## 5. Соответствие продуктовых возможностей коду

| Возможность | Где реализовано |
|-------------|-----------------|
| **Реестр активов** (asset registry) | `models/asset.py`, `services/assets.py`, `api/v1/assets.py`, `domain/assets/taxonomy.py` |
| **Condition intelligence** | `domain/observations/condition.py`, `Observation.condition_class/severity`, `services/reviews.py` |
| **Геопространственные данные** | `Geography`-колонки, `services/geospatial.py`, `api/v1/map.py`, `assets/nearby` |
| **История состояния** | `models/history.py`, `services/history.py`, `GET /assets/{id}/history` |
| **AI-инспекция** | `interfaces/ml_provider.py`, `infrastructure/ml/*`, `use_cases/processing/pipeline.py`, `api/v1/ml.py` |
| **Human-in-the-loop** | `models/review.py`, `domain/reviews/logic.py`, `services/reviews.py`, `api/v1/reviews.py` |
| **Active learning** | `models/training.py`, `services/reviews.py::_upsert_training_example` (сбор, без авто-дообучения) |
| **Приоритизация риска** | `domain/risk/scoring.py`, `services/risk.py`, `Asset.priority_band/current_priority` |
| **Change detection** | `services/history.py::record_change`, `AssetConditionHistory.is_physical_change` |
| **Аналитика покрытия** | `services/analytics.py::coverage`, `api/v1/analytics.py` |

## 6. Границы MVP и анти- scope

### В MVP (реализовано)
- Mock ML-провайдер (детерминированные синтетические детекции) и HTTP-провайдер внешнего сервиса.
- Эвристический quality gate (blur/разрешение/экспозиция на OpenCV).
- GPS-геолокация по треку из метаданных (CONFIRMED/ESTIMATED/UNAVAILABLE).
- Дедупликация `weighted-v1` (spatial/type/temporal/context/visual), без visual-embeddings.
- Append-only review, сбор training examples.
- Grid-эвристика покрытия по настроенной области.
- CSV/XLSX экспорт, GeoJSON-слои, Prometheus-метрики, health-пробы.

### Анти-scope (сознательно НЕ реализовано в MVP)
- **Авто-дообучение моделей** — только сбор проверенных пар (image, label).
- **Реальная анонимизация** лиц/номеров — `NoopPrivacyFilter` честно ставит `NOT_APPLIED`.
- **Map matching / визуальная локализация** — только GPS; точки расширения заложены.
- **Visual/embedding similarity** в дедупликации — `EmbeddingSimilarityProvider` бросает `NotImplementedError`.
- **Дорожная модель покрытия** — покрытие считается фиксированной сеткой, не по дорожной сети.
- **Автоматическое слияние** неоднозначных кандидатов (`AMBIGUOUS`) — запрещено политикой.
- **ML-фреймворки внутри backend** — инференс вынесен за контракт `schema_version 1.0`.

## 7. Точки расширения

| Точка | Интерфейс / место | Реализации MVP | Как расширять |
|-------|-------------------|----------------|---------------|
| **MLProvider** | `application/interfaces/ml_provider.py` (Protocol) | `MockMLProvider`, `HTTPMLProvider` | новая реализация + выбор в `ml/factory.py` (`ML_PROVIDER`) |
| **ObjectStorage** | `application/interfaces/storage.py` (Protocol) | `S3Storage`, `LocalFilesystemStorage` | новая реализация + `storage/factory.py` (`STORAGE_BACKEND`) |
| **JobQueue** | `application/interfaces/queue.py` (Protocol) | `RQJobQueue`, `InlineJobQueue` | новая реализация + `queue/factory.py` (`QUEUE_MODE`) |
| **PrivacyFilter** | `use_cases/processing/privacy.py` (Protocol) | `NoopPrivacyFilter` | реальная анонимизация; инъекция в `ProcessingPipeline` |
| **QualityGate** | `use_cases/processing/quality.py` (Protocol) | `HeuristicQualityGate` | обученная модель качества; инъекция в pipeline |
| **EmbeddingSimilarityProvider** | `services/deduplication.py` | заглушка (`NotImplementedError`) | визуальное сравнение; передаётся в `DeduplicationService` |
| **Таксономия активов** | `domain/assets/taxonomy.py::register_asset_type` | 5 типов | новый `AssetTypeDef` без изменения схемы БД (`asset_type` — VARCHAR) |
| **Таксономия дефектов** | `domain/defects/taxonomy.py::register_defect_type` | 10 типов | новый `DefectTypeDef` без изменения схемы БД |
| **Геолокация** | `services/geolocation.py` | GPS-интерполяция | map matching / visual localization; источники `MAP_MATCHING`, `VISUAL`, `MANUAL` уже в enum |

## 8. Связанные документы

- [Поток данных](data-flow.md) — pipeline обработки по стадиям.
- [Доменная модель](domain-model.md) — сущности, инварианты, state machines.
- [Диаграмма компонентов](component-diagram.md) — Mermaid-граф компонентов.
- [Sequence-диаграммы](sequence-diagrams.md) — ключевые сценарии.
- [Схема БД](../database/schema.md) — таблицы, constraints, индексы, enum.
- [Геопространственный слой](../database/geospatial.md) — PostGIS, координаты, GeoJSON.
- [ML-контракт](../integrations/ml-contract.md) — контракт интеграции с ML.
