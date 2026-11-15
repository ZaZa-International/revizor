# AGENTS.md — рабочий регламент для coding agents

Этот файл — инструкция для агентов и разработчиков, меняющих код. Это не маркетинг.
Читай перед любой задачей. Проверяй изменения командами из раздела «Проверки».

## 1. Что это за система

Backend мониторинга телеком-инфраструктуры МГТС: загрузка изображений/видео →
обработка в worker → ML-детекции (через контракт) → дедупликация физических объектов →
реестр Asset / Observation / Defect → risk scoring → проверка оператором → экспорт/аналитика.
Модульный монолит. ML — внешний сервис за интерфейсом. Очередь — Redis + RQ.

## 2. Слои и границы (нарушать нельзя)

```
app/api/v1/            → только HTTP: разбор запросов, вызов сервисов, сериализация.
app/application/       → сервисы и use cases; оркестрация; интерфейсы (порты) в interfaces/.
app/domain/            → чистая логика и enums. ЗАПРЕЩЕНЫ импорты fastapi, sqlalchemy,
                         redis, boto3, cv2, httpx и любых ML-фреймворков.
app/infrastructure/    → ORM-модели, репозитории, S3/local storage, ML-провайдеры, RQ.
app/schemas/           → публичные Pydantic-схемы API и ML-контракты.
app/core/              → security, logging, metrics, middleware, exceptions.
app/workers/           → entrypoint worker и задачи (тонкая обёртка над pipeline).
```

Правила зависимостей:
- Роутер не содержит бизнес-логики и SQL. Вся логика — в application/domain.
- ORM-модели (`infrastructure/database/models`) НИКОГДА не отдаются в API напрямую;
  только через `app/schemas` (конвертация в `api/v1/serializers.py`).
- Domain-сервисы получают данные аргументами, не ходят в БД сами.
- Application-сервисы работают с БД через репозитории, не через голый SQL в роутерах.
- Новые внешние интеграции — через порт в `application/interfaces/` + адаптер в `infrastructure/`.

## 3. База данных и миграции

- PostgreSQL 16 + PostGIS. География: `Geography(POINT/LINESTRING, srid=4326)`.
  Порядок координат ВСЕГДА (longitude, latitude). Не путать geometry и geography:
  расстояния в метрах — только geography (`ST_Distance`, `ST_DWithin`).
- Схема меняется ТОЛЬКО через Alembic (`backend/migrations/versions/`).
  `Base.metadata.create_all` в рантайме запрещён.
- Новая миграция: `uv run alembic revision -m "name"` (шаблон в migrations/script.py.mako),
  писать upgrade И downgrade. Enum-типы создавать через `postgresql.ENUM(...).create(bind, checkfirst=True)`
  и использовать `create_type=False` в колонках (см. 0001_initial.py).
- Имена constraint — по naming convention в `database/base.py`.
- Все datetime-колонки timezone-aware (`type_annotation_map` в Base). Не создавать naive.
- Типы объектов/дефектов/состояний — VARCHAR + реестры в `domain/assets/taxonomy.py`,
  `domain/defects/taxonomy.py`, `domain/observations/condition.py`. Новый тип НЕ требует
  миграции. Статусы/роли — native PG enums (добавление значения = миграция).
- AuditLog и Review — append-only. Не добавлять UPDATE/DELETE пути.
- Идемпотентность: `job_frames UNIQUE(job_id, frame_index)`,
  `observations` partial UNIQUE `(processing_job_id, detection_id)`,
  `uploads.checksum_sha256 UNIQUE`, таблица `idempotency_keys`. Не ломать эти ограничения.
- Оптимистичная блокировка Asset: колонка `version`; обновления через
  `update(...).where(version == expected).returning(id)`.

## 4. API

- Версия `/api/v1`. Единый формат ошибок: `{"error": {code, message, details, request_id}}`
  (обработчики в `api/errors.py`). Новые ошибки — наследники `AppError` с уникальным code.
- Пагинация: `page`, `page_size` (≤100), envelope `{items, total, page, page_size, pages}`.
  Сортировка — только по whitelist полей репозитория. Фильтры — query-параметры.
- GeoJSON: `type: FeatureCollection`, координаты `[lon, lat]`. bbox-фильтр:
  `bbox=min_lon,min_lat,max_lon,max_lat`.
- Публичные схемы менять осторожно: это контракт frontend. Ломающее изменение →
  обновить `docs/integrations/frontend-contract.md`, `contracts/openapi/openapi.json`
  (`make openapi`), контрактные тесты, CHANGELOG.
- Новый endpoint: роутер в `api/v1/`, подключить в `api/v1/router.py`, схемы в `app/schemas/`,
  логика в сервисе, RBAC через `require_roles`/`OperatorOrAdmin`/`CurrentUser`,
  тесты в `tests/api/`. Теги OpenAPI обязательны.
- Небезопасные POST (uploads/jobs/reviews) поддерживают `Idempotency-Key` через
  `api/v1/idempotency.py`. Новый такой endpoint — использовать тот же helper.
- Секреты, токены, пароли, содержимое изображений не логировать
  (redaction-процессор в core/logging есть, не полагаться только на него).

## 5. ML-контракт

- Контракт v1.0: `app/schemas/ml.py`, JSON Schema в `contracts/ml/`,
  документ `docs/integrations/ml-contract.md`. Менять контракт можно ТОЛЬКО с
  обновлением схем, примеров, контрактных тестов и документации; ломающие изменения —
  новая `schema_version`.
- Backend не знает, что внутри ML (YOLO/PyTorch/ONNX). Никаких ML-библиотек в зависимостях backend.
- Новый провайдер: реализовать `MLProvider` protocol, зарегистрировать в
  `infrastructure/ml/factory.py`, покрыть тестами по образцу `tests/unit/test_ml_providers.py`.
- Ошибки ML: `MLTimeoutError`/`MLUnavailableError` (retryable), `MLContractError` (не retryable),
  `MLInferenceError`. Не глотать их в pipeline — кадр помечается FAILED.
- bbox — абсолютные пиксели исходного изображения; confidence ∈ [0,1]; severity ∈ [1,5];
  detection_id уникален в ответе. Пустой detections — валидный результат, не ошибка.

## 6. Pipeline и worker

- Стадии — отдельные ответственности (`application/use_cases/processing/`).
  Не сливать pipeline в один монолитный метод.
- Покадровые ошибки не валят job: статусы PROCESSED/REJECTED/FAILED в `job_frames`,
  итог COMPLETED/PARTIALLY_COMPLETED/FAILED.
- Повторный запуск job обязан быть идемпотентным (пропуск обработанных кадров,
  unique по detection_id). Новые стадии — сохранять это свойство.
- Отмена кооперативная: pipeline проверяет статус CANCELLED каждые 10 кадров.
- Quality gate и Privacy filter — интерфейсы. NoopPrivacyFilter честно ставит
  NOT_APPLIED. ЗАПРЕЩЕНО помечать анонимизацию APPLIED без реальной обработки.
- Без GPS — статус UNAVAILABLE, координаты не выдумывать.
- Тяжёлая обработка — только в worker (RQ). `QUEUE_MODE=inline` — для тестов/dev.

## 7. Тесты

- Маркеры: `unit` (без сервисов), `integration`, `api`, `contract`.
  Integration/API/contract идут против РЕАЛЬНЫХ PostgreSQL/PostGIS, Redis, S3.
  SQLite запрещён. Тестовая БД `mgts_infra_test` создаётся conftest автоматически.
- Не писать фиктивные тесты и не отключать проверки ради зелёного прогона.
- Новый функционал → unit на доменную логику + integration/api на сценарий +
  contract при изменении контрактов. Граничные случаи обязательны
  (нет GPS, swap координат, дубли, повторная обработка, ошибки ML/storage, конкурентные update).
- Фикстуры: `tests/conftest.py` (client, admin_headers, operator_headers, viewer_headers,
  database, settings), `tests/fixtures/media.py` (синтетические jpeg/mp4/GPS),
  `tests/fixtures/ml_stub.py` (детерминированный ML).

## 8. Запрещённые решения

1. Микросервисы, Kubernetes, вторая очередь (Celery рядом с RQ).
2. ML-фреймворки в зависимостях backend; обучение моделей в этом репозитории.
3. Бизнес-логика в роутерах; ORM в ответах API; SQL в роутерах.
4. `create_all` вместо миграций; изменение схемы руками в БД.
5. Авто-объединение AMBIGUOUS/POSSIBLE_MATCH дедупликации.
6. Перезапись истории review/audit; затирание исходных ML-предсказаний.
7. Автоматические заявки на ремонт по неподтверждённым предсказаниям; авто-переобучение.
8. Выдуманные координаты при отсутствии GPS; перестановка lon/lat.
9. Хранение бинарных файлов в PostgreSQL; пароли открытым текстом; фиксированный prod JWT-secret.
10. Коммит `.env`, секретов; отключение тестов/линта ради сборки.
11. Black/isort (форматирование — только Ruff); комментарии без необходимости.

## 9. Проверки (запускать перед завершением любой задачи)

```bash
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run pytest -m unit                 # быстро, без сервисов
uv run pytest                         # полностью (infra: docker compose up -d db redis s3 s3-init)
```

Из корня: `make lint`, `make test`. Миграции: `uv run alembic upgrade head`
(+ проверка `downgrade base && upgrade head` при изменении схемы).
Docker: `docker compose build backend`. OpenAPI: `make openapi` (коммитить обновлённый JSON).

## 10. Типовые задачи

- **Новый тип объекта**: `register_asset_type(AssetTypeDef(...))` в taxonomy.py →
  при необходимости condition/defect маппинг → тесты → seed при желании. Миграция не нужна.
  Док: `docs/development/adding-new-asset-type.md`.
- **Новый дефект**: `register_defect_type(...)` + `CONDITION_DEFECT_MAP`. Док: adding-new-defect-type.md.
- **Новый endpoint**: раздел 4. **Новая сущность**: модель → миграция → репозиторий →
  сервис → схемы → роутер → тесты → docs/database/schema.md.
- **Изменение risk-формулы**: только в `domain/risk/scoring.py`, поднять `RISK_POLICY_VERSION`,
  факторы сохраняются в `assets.priority_factors`. Не выдавать формулу за отраслевой стандарт.
- **Изменение дедупликации**: веса/пороги в `domain/deduplication/policy.py` + config;
  explanation обязан оставаться машиночитаемым; тесты на AMBIGUOUS обязательны.

## 11. Окружение

Конфиг — `app/config.py` (pydantic-settings, env). `.env.example` — источник истины по
переменным. Dev-инфраструктура: `docker compose up -d db redis s3 s3-init`
(S3 = SeaweedFS; MinIO-совместимый API, см. ADR-0006). Порты: 5432, 6379, 9000 (S3), 8000 (API).
Python 3.12 через uv (`uv sync`). Не добавлять зависимости без обоснования в PR/ADR.
