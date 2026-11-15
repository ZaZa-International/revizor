# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.1.0] - 2026-11-15

Первый выпуск MVP: полный цикл drive-by инспекции телеком-инфраструктуры —
от загрузки фото/видео до каталога активов с приоритетами и review-цикла.

### Added

#### Аутентификация и безопасность
- Логин по паролю (Argon2id), JWT HS256 access-токены (TTL 60 мин, `jti`, `type=access`).
- RBAC: роли `ADMIN`, `OPERATOR`, `VIEWER`, `SERVICE`; зависимости FastAPI для проверки ролей.
- Bootstrap-администратор при первом старте (только если пользователей нет и задан пароль).
- Обязательный `JWT_SECRET_KEY` в production (без него приложение не стартует); эфемерный случайный ключ в dev.
- Rate limiting: логин 10/мин на IP, загрузка 30/мин на пользователя (Redis sliding window, 429 + Retry-After).
- Аудит действий (`audit_logs`): create/update/delete/review/login/export/job retry/cancel.
- Валидация загрузок: лимит 2 ГиБ, санитизация имени файла, соответствие расширение ↔ MIME ↔ magic bytes (JPEG/PNG/WebP/MP4/AVI/WebM/MOV).
- Редакция секретов в логах; `pip-audit` в CI (строгий режим, еженедельно); pre-commit hooks.

#### Загрузка и обработка
- Загрузка изображений и видео (multipart) с метаданными съёмки (GPS-трек, время, курс, скорость).
- Дедупликация загрузок по SHA-256 (unique checksum); идемпотентность `Idempotency-Key` для POST uploads/jobs/reviews (unique key+user+endpoint, replay ответа).
- Очередь обработки RQ (воркер-процесс, ретраи через scheduler: max 3, интервалы 10/30/60 с, timeout 1800 с); inline-режим для тестов/dev.
- Pipeline: извлечение кадров (OpenCV, интервал 1 с, до 2000 кадров) → quality gate (резкость, экспозиция, разрешение) → privacy-фильтр → ML-инференс → нормализация состояний → трекинг → геолокация → дедупликация → risk scoring → персистентность.
- Геолокация кадров из GPS-трека: интерполяция, статусы CONFIRMED/ESTIMATED/UNAVAILABLE/INVALID; без данных координаты не выдумываются; точки расширения map matching / visual localization.
- Статусы задач (PENDING/QUEUED/PROCESSING/COMPLETED/PARTIALLY_COMPLETED/FAILED/CANCELLED), прогресс, стадии, кооперативная отмена, повтор; покадровые сбои не валят задачу.
- Идемпотентность обработки: unique (job_id, frame_index), частичный unique (job_id, detection_id).

#### ML-интеграция (контракт v1.0)
- Протокол `MLProvider`; провайдеры `mock` (детерминированные синтетические детекции) и `http` (внешний сервис).
- Контракт v1.0: Pydantic-модели, JSON Schema (draft 2020-12) в `contracts/ml/`, эталонные примеры, контрактные тесты; документ `docs/integrations/ml-contract.md`.
- HTTP-провайдер: эндпоинты /v1/health, /v1/model-info, /v1/infer, /v1/infer/batch; ретраи таймаутов/connect/5xx с backoff+jitter; 4xx не повторяются; таксономия ошибок (timeout/unavailable/contract/inference).
- Передача кадров по ссылке `storage_key` (без байтов по HTTP); batch с частичными ошибками; пустой результат — валидный.
- Эндпоинты `/api/v1/ml/health`, `/api/v1/ml/model-info`.

#### Каталог активов и дефекты
- Реестры типов активов и дефектов в коде (VARCHAR-колонки, новые типы без миграций): telecom_well, pole, telecom_cabinet, cable_line, other; 10 типов дефектов.
- Активы: PostGIS geography(POINT, 4326), статусы геолокации, текущее состояние/severity, приоритет и полоса, lifecycle, display_name, external_id.
- Дедупликация: взвешенная политика (spatial .55 / type .20 / temporal .05 / context .15 / visual .05), пороги 0.70/0.45, per-type радиусы; AMBIGUOUS никогда не сливается автоматически; объяснение решения сохраняется в наблюдении; точка расширения эмбеддингов.
- Risk scoring: прозрачная версионируемая формула (severity_norm × impact_factor × confidence_factor), полосы HIGH/MEDIUM/LOW + NEEDS_REVIEW (низкая уверенность/неизвестная severity/неоднозначная дедупликация); проектная эвристика, не отраслевой стандарт.
- Ручное переопределение приоритета с обязательной причиной; оптимистичная блокировка (expected_version); история изменений состояния/приоритета.
- Дефекты: автоматическое создание/обновление из состояний ML (CONDITION_DEFECT_MAP), статусы OPEN/CONFIRMED/IN_PROGRESS/RESOLVED/REJECTED, severity, связь с наблюдениями.
- Нормализация состояний ML: канонический словарь + алиасы, неизвестное → unknown; severity по умолчанию для состояний.

#### Наблюдения и review
- Наблюдения: исходные предсказания неизменяемы (raw_model_payload, confidence, severity, model name/version), bbox в пикселях, кропы детекций, геопривязка, dedup result/score/explanation.
- Append-only reviews: CONFIRMED / REJECTED / CORRECTED / NEEDS_MORE_INFORMATION; корректировки типа/состояния/дефекта/severity с валидацией против реестров; эффективное состояние отдельно от оригинала.
- Training examples из подтверждённых/исправленных наблюдений (PENDING → EXPORTED): контролируемый сбор данных для обучения, без автоматического retrain.

#### Карта, аналитика, экспорты
- Карта: GeoJSON-слои активов/наблюдений, bbox-фильтры, порядок координат (longitude, latitude).
- Маршруты съёмки: создание, просмотр, связь с загрузками/задачами.
- Аналитика: обзор, аналитика дефектов, покрытие территории (сетка 250 м, demo bbox).
- Экспорты CSV/XLSX (активы, наблюдения, дефекты) с теми же фильтрами, что и list-эндпоинты; лимит 50 000 строк; аудит экспорта; секреты не экспортируются.

#### Хранилище
- Абстракция `ObjectStorage`: S3 (boto3, path-style, presigned URL с TTL) и local-бэкенд (защита от path traversal).
- Раскладка ключей: uploads/{id}/, frames/{job}/, crops/{job}/; бинарные данные не в PostgreSQL.
- Dev-хранилище SeaweedFS вместо MinIO (публичная дистрибуция MinIO прекращена; проверено 2026-11-15); любой S3-сервер заменяется через окружение; init бакета (s3-init + ensure_bucket).
- Аутентифицированная выдача файлов `GET /api/v1/files/{key}`; presigned-ссылки в ответах API.

#### Приватность
- Статусы анонимизации NOT_APPLIED/APPLIED/FAILED/SKIPPED на каждом кадре/кропе.
- MVP: NoopPrivacyFilter честно помечает кадры NOT_APPLIED (анонимизация не выполняется); точка расширения PrivacyFilter.
- Документ `docs/security/privacy.md`: хранение, доступ, рекомендации retention и GDPR-подобные соображения.

#### Наблюдаемость и эксплуатация
- Структурированные логи structlog (JSON/console) с контекстом request_id/job_id/actor_id и редакцией секретов.
- Prometheus-метрики (`/metrics`): задачи, кадры, детекции, ML-латентность/ошибки, длина очереди.
- OpenTelemetry (опционально): трассировка FastAPI/SQLAlchemy/httpx, OTLP HTTP exporter.
- Health-эндпоинты: /health/live, /health/ready (DB/Redis/storage), /health (агрегат).
- docker-compose: db (PostGIS 16-3.4), redis 7, s3 (SeaweedFS), s3-init, backend, worker; dev-оверлей с hot reload.
- Alembic-миграции (обратимые, roundtrip в CI); Makefile (bootstrap/up/dev/migrate/seed/test/lint/format/typecheck/openapi); скрипты bootstrap/dev/test/lint/seed_demo/export_openapi.
- CI: lint (ruff) + typecheck (mypy), тесты на service containers PostGIS+Redis, migration roundtrip, docker build; security workflow (pip-audit).

#### Тесты и документация
- 262 теста: unit 108 / integration 35 / api 83 / contract 36; реальная тестовая БД mgts_infra_test (авто-создание + миграции), Redis db 15, local storage, inline-очередь, mock ML; TRUNCATE-изоляция между тестами.
- Контрактные тесты ML (JSON Schema ↔ Pydantic ↔ примеры) и frontend (конверт ошибок, пагинация, GeoJSON, сквозные сценарии).
- Документация: контракт ML, разработка (testing, добавление типов активов/дефектов/ML-провайдера), хранилище, приватность, эксплуатация (deployment, local-development, troubleshooting), ADR-0001…ADR-0012, SECURITY.md, CONTRIBUTING.md, MIT LICENSE.

### Known limitations

- Анонимизация лиц/номеров не выполняется (NOT_APPLIED); реальный PrivacyFilter — точка расширения.
- Mock ML-провайдер — синтетические детекции, не инференс; реальная модель подключается через ML_PROVIDER=http.
- Аутентификация backend ↔ ML отсутствует (доверенная приватная сеть); refresh-токенов и revocation нет.
- Автоматических политик retention/удаления данных нет; справочных эндпоинтов типов и управления пользователями нет.
- Risk scoring — проектная эвристика, не калибрована на статистике отказов.

[Unreleased]: https://github.com/ZaZa-International/revizor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ZaZa-International/revizor/releases/tag/v0.1.0