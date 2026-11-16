# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### 0.2.0 — усиление безопасности и надёжности по аудиту backend'а

Исправления аудита (`docs/audit/backend-audit.md`), Developer Portal, контрактное
tooling, regression-тесты и production-hardening. Breaking pre-1.0 изменения
перечислены ниже; все проверены локальным CI (`scripts/ci_local.sh`, 12/12 PASS).

### Added

#### Безопасность
- `POST /api/v1/auth/logout` + denylist `jti` в Redis (TTL до `exp`), проверка при аутентификации; при недоступности Redis — fail-open (документировано).
- Body-limit middleware: отказ 413 **до аутентификации** и без полной буферизации — multipart (`MAX_UPLOAD_SIZE_BYTES`) и JSON (`MAX_JSON_BODY_BYTES`, 2 MiB).
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP `frame-ancestors`; HSTS — на proxy.
- Per-username throttle логина (`RATE_LIMIT_LOGIN_PER_USERNAME_PER_MINUTE=20`) в дополнение к IP-лимиту; in-memory fallback rate limiter'а при недоступности Redis (process-wide).
- Строгий production-валидатор конфигурации: отказ старта при пустом/placeholder `JWT_SECRET_KEY` или длине < 32, placeholder/коротком (< 12) `BOOTSTRAP_ADMIN_PASSWORD`, S3-credentials `minioadmin`, `QUEUE_MODE=inline`, `'*'` в `CORS_ORIGINS`. `.env.example` — пустые секреты вместо placeholder'ов.
- Защита от memory bomb в worker: probe размерности до decode, лимиты `PROCESSING_MAX_IMAGE_PIXELS` (64 Мп) / `PROCESSING_HARD_MAX_FRAME_SIDE` (8192), downscale кадра до `PROCESSING_MAX_FRAME_SIDE` (4096); оригинал в хранилище не изменяется, bbox — в пикселях сохранённого кадра.

#### Надёжность и геоданные
- Fencing исполнения job (advisory lock): двойная обработка живого job исключена; статус `PROCESSED` никогда не понижается в `FAILED`.
- Stale-sweeper: зависшие `PROCESSING`/`QUEUED` без живого RQ-исполнения → `FAILED` (`stale_*`) через `RQ_JOB_TIMEOUT + STALE_JOB_GRACE_SECONDS` (1920 с по умолчанию); retry stale `PROCESSING` разрешён напрямую.
- Write-ahead сохранение ML-ответа и детерминированный `request_id` — идемпотентность повторной инференции не зависит от провайдера.
- Prometheus-метрики worker'а на `WORKER_METRICS_PORT` (9100).
- `S3_PUBLIC_ENDPOINT_URL`: presign отдельным client'ом через публичный endpoint (браузер больше не получает internal hostname `s3`); presign только GET, expiry из `S3_PRESIGN_EXPIRES_SECONDS`.
- GPS: UTC-нормализация naive timestamps (assume-UTC, job больше не падает); accuracy gate `GPS_MAX_ACCURACY_M` (50 м) → `ESTIMATED`; отклонение не-finite `accuracy_m`/`heading_deg`/`speed_mps`.
- Дедупликация: батчинг evidence-запросов, `DEDUP_MAX_CANDIDATES=50`, grid advisory lock против конкурентных дублей, `same_route` по EXISTS (любой job наблюдения).
- Скрипты `scripts/backup.sh` (pg_dump -Fc + S3 sync, retention 14 дампов) и `scripts/restore.sh` (подтверждение, pg_restore --clean --if-exists + S3 sync обратно); runbook restore-drill в deployment.md.

#### API
- Заголовок `X-Export-Truncated: true` при усечении экспорта лимитом 50 000 строк.
- Пагинация (envelope `{items, total, page, page_size, pages}`) для кадров job и истории актива; фильтр по статусу кадров.
- Валидация: неизвестный `sort_by` → 422 (вместо тихого fallback), `date_from > date_to` → 422, `Idempotency-Key` > 128 символов → 422.
- Idempotency: fingerprint запроса — replay с другим payload → 409 `idempotency_conflict`; presigned-URL при replay перегенерируются (не протухшие).

### Changed — breaking pre-1.0

- **Кадры job и история актива**: вместо голых массивов — pagination envelope.
- **VIEWER больше не получает медиа-URL** (presigned/image/crop) и доступ к `GET /files/{key}` — только метаданные; медиа доступны OPERATOR/ADMIN/SERVICE (кадры не анонимизированы).
- **Cross-user дедупликация по checksum** возвращает нейтральную запись (`id`, `created: false`) без чужих метаданных и URL.
- **Удаление загрузки** — только загрузивший пользователь или ADMIN (403 иначе).
- **Неизвестный `sort_by`** → 422 вместо сортировки по умолчанию; инвертированный date-range → 422.
- **Idempotency replay с другим payload** → 409 вместо возврата старого ответа.
- **Presign только GET** (PUT-presign capability удалена).
- **Базовый compose больше не публикует infra-порты** (5432/6379/9000/9333) на хост — только явный dev-override (`make dev`, bootstrap/test.sh используют его). API по-прежнему на 8000.

### Fixed

- REJECTED review: приоритет 0, состояние актива — из последнего неотклонённого состояния; записи истории REJECTED с `is_physical_change=False` (ADR-0007, поправка 0.2.0).
- `scripts/test.sh`: Redis по умолчанию db **15** (FLUSHDB тестов больше не стирает dev-очередь в db 0).
- Документация: полный inventory переменных в `.env.example`; testing.md — CI действительно поднимает S3 (localstack:4566), unit-тесты автономны, `TEST_DB_NAME` для параллельных прогонов; `DEBUG` документирован как флаг debug FastAPI; pip-audit переведён в `--strict` режим; исправлен mismatch имён файлов в инструкции по backup; слепое пятно swap-детекции (оба значения в диапазоне) документировано в geospatial.md.
- Cancel job: refresh после flush (устранён MissingGreenlet 500 при успешной отмене).
- Concurrent reviews: атомарный upsert training examples (ON CONFLICT) + advisory-lock идемпотентности — конкурентный replay с тем же ключом возвращает тот же review, а не 409.
- Метрики worker'а: multiprocess-режим prometheus_client — счётчики fork'нутых work-horse реально агрегируются на `:9100/metrics` (ранее были невидимы из-за fork).

### Added — волна 2/3 (Developer Portal, контракты, QA, DevOps)

- **OpenAPI Developer Portal**: кастомный Swagger UI (`/docs`) в фирменной тёмно-синей/графитовой палитре MGTS (wordmark, версия, среда, ссылки на документацию, favicon), 14 упорядоченных секций с workflow-описаниями, описания всех 47 операций, стабильные operationId, 320+ примеров, декларации ошибок (401/403/404/409/422/429/5xx) с `ErrorResponse` вместо `HTTPValidationError`, typed GeoJSON/analytics/health схемы, binary media types для exports/files, enum-описания, `persistAuthorization` + рабочий Try it out (проверено в браузере).
- **Contracts tooling**: `scripts/check_openapi.py` (drift live↔committed), `scripts/check_breaking.sh` (oasdiff против base-ветки), `scripts/generate_ts_client.sh` (openapi-typescript → `contracts/typescript/schema.d.ts` + openapi-fetch README), 18 эталонных примеров ответов `contracts/examples/api/`, контрактные тесты OpenAPI (29), `docs/api/` (7 документов: overview, authentication, errors, pagination-filtering, geospatial, upload-and-processing, workflows), `docs/integrations/README.md` — точка входа для frontend/ML команд.
- **QA**: 164 новых теста — security regression (JWT tamper/alg-none/role-escalation, logout, ownership, VIEWER gating, redacted dedup, body limits 413, headers, NaN/Inf, CSV injection, per-username 429), полная role×endpoint matrix (119), failure modes (queue/Redis/S3/PG down, corrupted video, max size, stale recovery), concurrency (gather PATCH race, active-upload guard, idempotent review replay, concurrent dedup → 1 asset). Итого **661 тест**.
- **DevOps**: one-shot `migrate` сервис с advisory lock (гонка миграций при scale исключена), Redis appendonly, `stop_grace_period` worker 300s, pin образов (seaweedfs:4.53, aws-cli:2.40.3, uv:0.13.8, localstack:4.3.0), s3-init с верификацией бакета, Dockerfile HEALTHCHECK + cleanup, CI: OpenAPI drift + TS drift + oasdiff breaking + smoke job, `pip-audit --strict`, `scripts/ci_local.sh` — полный локальный CI (12 шагов, все PASS), `scripts/smoke.sh` (end-to-end против стека), `scripts/load_smoke.py` (p50/p95/error-rate).
- **Рефакторинг**: pipeline декомпозирован на оркестратор + `FramePersistence` + `JobProgressTracker`; N+1 устранены (batch StoredFile/defect counts/dedup evidence); `DefectService`/`RouteService`; общие pagination/serializer helpers.

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