# Backend Audit — MGTS Infrastructure Intelligence

Дата: 2026-11-16. Аудит проведён по фактическому исходному коду (не по README/отчётам):
6 независимых направлений (архитектура/БД, безопасность, API-контракты, надёжность
worker'ов, геоданные/производительность, DevOps/CI/тесты) + верификация лидом.
Методы: чтение кода, in-memory интроспекция приложения/Pydantic/установленных библиотек,
read-only psql EXPLAIN на dev-БД, трассировка RQ 3.0/botocore/Starlette internals,
воспроизведение сценариев в памяти без записи. Статика: ruff/mypy — clean на момент аудита.

Легенда серьёзности: CRITICAL / HIGH / MEDIUM / LOW.
Приоритеты исправлений: **P0** (блокирует безопасную работу), **P1** (надёжность/корректность),
**P2** (качество/производительность), **P3** (косметика).

Статусы: `OPEN` → исправляется в текущей волне; `FIXED` — проверено тестом (см. раздел 8).

---

## 1. P0 — блокирует безопасную работу

### SEC-1 — HIGH — Unauthenticated disk exhaustion: multipart буферизуется до auth/лимитов
- **Файлы:** `backend/app/api/v1/uploads.py:42-55`; `backend/app/application/services/uploads.py:109-114`; `backend/app/main.py:86-94` (нет body-limit middleware).
- **Описание:** FastAPI читает тело запроса ДО разрешения зависимостей auth (`fastapi/routing.py:453-458` → `:511`). Starlette `MultiPartParser` применяет `max_part_size` только к не-файловым частям; файловые части пишутся в `SpooledTemporaryFile` без ограничения (проверено в installed starlette 1.10). Лимит 2GiB и rate limit проверяются только в handler'е, который выполняется после полной буферизации.
- **Сценарий:** `curl -X POST /api/v1/uploads -F "file=@/dev/zero;filename=x.jpg"` без токена, 100GB stream → сервер спулит всё в /tmp и лишь затем вернёт 401. Повторить конкурентно.
- **Последствия:** исчерпание диска контейнера/хоста; падают uploads, RQ, логи, потенциально PostgreSQL на том же volume. DoS без аутентификации.
- **Исправление:** ASGI middleware: ранний отказ по `Content-Length` (> лимита → 413) + счётчик полученных байтов с abort при превышении (multipart: `max_upload_size_bytes`+1MB overhead; JSON: `max_json_body_bytes`). Документировать edge-лимит nginx.
- **Тест:** API: multipart больше лимита без токена → 413, spool не растёт выше лимита; unit middleware с counting receive.

### SEC-2 — HIGH — Unauthenticated memory exhaustion: JSON-тела буферизуются целиком
- **Файлы:** `backend/app/api/v1/auth.py:14-26` (публичный login); `fastapi/routing.py:458` (`await request.body()` до валидации); middleware отсутствует.
- **Сценарий:** `POST /api/v1/auth/login` с JSON-телом 2GB → полное буферизование в RAM до `LoginRequest`/rate limit. Несколько конкурентных запросов → OOM API.
- **Последствия:** DoS без аутентификации (память).
- **Исправление:** тот же body-limit middleware (SEC-1), JSON-лимит ~2MB.
- **Тест:** oversized JSON на /auth/login → 413 без полного буферизования.

### SEC-3 — CRITICAL — Placeholder-секреты проходят production-валидатор
- **Файлы:** `.env.example:38,42` (`change-me-in-production`, `change-me-admin`); `backend/app/config.py:109-115` (отклоняется только ПУСТОЙ секрет); `scripts/bootstrap.sh:23-26` (cp example → .env).
- **Сценарий:** деплой по README: `cp .env.example .env`, `APP_ENV=production`, старт. (а) Вход `admin/change-me-admin` (bootstrap создаётся). (б) HS256-секрет публичен в репозитории → форжинг токена для любого UUID (UUID reviewer'ов видны любому VIEWER через `GET /reviews`) → полный доступ.
- **Последствия:** полный обход аутентификации/эскалация на любом деплое, оставившем placeholder.
- **Исправление:** валидатор production: отклонять известные placeholders (`change-me*`, `minioadmin` для S3), минимальная длина секрета ≥32; `.env.example` с ПУСТЫМИ `JWT_SECRET_KEY`/`BOOTSTRAP_ADMIN_PASSWORD`; placeholder bootstrap-пароль в production → отказ старта.
- **Тест:** unit `Settings(app_env="production", jwt_secret_key="change-me-in-production")` → raise; аналогично bootstrap/S3.

### SEC-4 — CRITICAL — Compose публикует Redis/S3/PG без auth на host-портах
- **Файлы:** `docker-compose.yml:34-35` (5432, mgts/mgts), `:48-49` (6379 без requirepass), `:67-69` (9000/9333, SeaweedFS без S3-auth); RQ trust boundary: `backend/app/infrastructure/queue/rq_queue.py:25-36`, `backend/app/workers/worker.py:16-19` (RQ сериализует job pickle).
- **Сценарий:** доступ к портам демо-хоста (конференц-Wi-Fi, облачная VM с открытой SG): (а) crafted `rq:job:<id>` в Redis → worker исполняет произвольный callable → RCE как appuser (доступ к БД/S3/изображениям); (б) анонимный S3 GET → дамп всех фото/видео; (в) `psql postgres://mgts:mgts@host:5432/mgts_infra` → полная БД.
- **Последствия:** RCE + полная компрометация данных в дефолтном демо-деплое.
- **Исправление:** базовый compose — infra БЕЗ host-портов (internal network); публикация портов только в явном dev-override (`docker-compose.dev.yml`), bootstrap/test.sh используют override; Redis `appendonly yes` для durability очереди; документировать.
- **Тест:** CI compose-lint: базовый файл не публикует infra-порты; интеграционный тест AUTH Redis (в dev-override).

### SEC-5 — HIGH — Memory bomb worker'а: decode изображений без лимита размерности
- **Файлы:** `backend/app/application/use_cases/processing/frames.py:52-56,62-83`; `backend/app/application/use_cases/processing/quality.py:40-43` (Laplacian CV_64F = 8 байт/пиксель); `backend/app/schemas/ml.py:24-25` (le=32768 — только метаданные ПОСЛЕ decode).
- **Сценарий:** OPERATOR загружает solid-color JPEG 30000×30000 (~1-5MB, проходит лимит 2GiB), создаёт job. Worker: imread COLOR ≈2.7GB + grayscale ≈0.9GB + Laplacian float64 ≈7.2GB → OOM. Retry бесплатен → повторные убийства worker'ов. Проверено: `OPENCV_IO_MAX_IMAGE_PIXELS` default 2^30, 32768² = ровно 2^30 → проходит.
- **Последствия:** аутентифицированный DoS всего processing tier; в inline-режиме — гибель API.
- **Исправление:** дешёвый probe размерности ДО decode (JPEG SOF parse / VideoCapture props), отклонение > `processing_max_image_pixels` (64MP) / side > 8192; downscale кадра до longest side ≤ `processing_max_frame_side` (4096) для обработки (оригинал в storage не трогаем); явный `OPENCV_IO_MAX_IMAGE_PIXELS`; blur на downscaled.
- **Тест:** unit: synthetic large-dimension JPEG header → reject до imdecode (spy); integration: oversized image → REJECTED/FAILED без аллокации.

### GEO-2 — HIGH — Presigned URLs содержат internal Docker hostname
- **Файлы:** `docker-compose.yml:15` (`S3_ENDPOINT_URL=http://s3:9000`); `backend/app/infrastructure/storage/s3.py:28-39,102-112`; потребители `api/v1/uploads.py:36`, `api/v1/serializers.py:38`.
- **Сценарий:** любой compose-деплой: frontend получает `http://s3:9000/mgts-infra/...?X-Amz-...` — host недостижим из браузера. Воспроизведено (presign — чистая computation). SigV4 подписывает Host → client-side rewrite ломает подпись.
- **Последствия:** все изображения/кропы битые в Docker-деплое (продукт не работает визуально).
- **Исправление:** `s3_public_endpoint_url` в config; второй boto3 client только для presign; fallback на internal когда не задан; compose dev задаёт `http://localhost:9000`; документация.
- **Тест:** unit: internal endpoint + public endpoint → host в URL = public; integration против S3.

### GEO-1 — HIGH — Naive GPS timestamps валят весь job
- **Файлы:** `backend/app/application/services/geolocation.py:40,58,80-81`; `backend/app/application/use_cases/processing/pipeline.py:146,222-229,268`.
- **Сценарий:** `gps_track` с ISO timestamps без Z/offset (типичный экспорт устройств) → naive datetime → `p.timestamp - observed_at` (aware) → TypeError → каждый кадр FAILED → job FAILED. Mixed track → TypeError на sort → job FAILED pipeline_error. Naive `capture_started_at` → падение в dedup. Воспроизведено агентом на реальном коде.
- **Последствия:** тихий обрыв качества данных, нет частичного восстановления.
- **Исправление:** UTC-нормализация naive timestamps в `parse_track` и `_resolve_start` (политика assume-UTC, документировать); тесты naive/mixed.
- **Тест:** unit: naive-only/mixed track, naive capture_started_at → CONFIRMED/invalid-count без исключений.

### REL-5 — HIGH — Конкурентные job'ы одного upload → дубли Asset; pipeline обходит version
- **Файлы:** `backend/app/application/services/jobs.py:37-55` (нет active-job guard); `migrations/versions/0001_initial.py:162-175` (только не-unique ix_upload_id); `backend/app/application/services/deduplication.py:83-118` + `repositories/assets.py:96-118` (READ COMMITTED: оба видят 0 candidates → оба NEW_ASSET); `pipeline.py:386-398,484-513` (insert без constraint; мутации Asset без version bump).
- **Сценарий:** два POST /jobs с разными ключами → два worker'а → два Asset для одного физического объекта; операторский expected_version слеп к ML-записям (version не растёт) → lost updates.
- **Последствия:** дубли реестра, нарушение оптимистичной блокировки (AGENTS §3).
- **Исправление:** миграция 0002: partial unique `(upload_id) WHERE status IN (PENDING,QUEUED,PROCESSING)` + 409 в create/retry; cross-upload гонка: `pg_advisory_xact_lock` на grid-cell (type+geohash) в транзакции кадра вокруг match+insert; version bump (или FOR UPDATE) при pipeline/review мутациях Asset.
- **Тест:** API: два job одного upload → 409; integration: два конкурентных pipeline → 1 asset; gather PATCH race.

### REL-3 — HIGH — Нет fencing исполнения: двойная обработка живого job
- **Файлы:** `backend/app/application/use_cases/processing/pipeline.py:112-116` (takeover = только warning), `:168-173` (cancel-check ищет CANCELLED), `:182-193,586-591` (PROCESSED→FAILED перезапись); `services/jobs.py:82-90` (rq_job_id перезаписывается, старое исполнение не отменяется).
- **Сценарий:** cancel→retry зависшего-но-живого job: retry ставит QUEUED→PROCESSING, оригинальный worker больше не видит CANCELLED → оба исполнения работают конкурентно; IntegrityError на uq_job_frame_index → проигравший перезаписывает PROCESSED победителя в FAILED → повторная инференция → дубли observation (новые detection_id) + дубли asset.
- **Последствия:** corruption статусов кадров/счётчиков, дубли, сломанная идемпотентность при конкуренции.
- **Исправление:** `pg_try_advisory_lock(hashtextextended(job_id::text,0))` на отдельном connection на всё время run(); не получен → skip; `_record_frame` НИКОГДА не понижает PROCESSED→FAILED.
- **Тест:** integration: два конкурентных run() с медленным ML stub → второй skip, counts как у одиночного.

### REL-1 — HIGH — Зависшие PROCESSING/QUEUED: медленное/условное автовосстановление, permanent tail
- **Файлы:** `pipeline.py:116-125`; `services/jobs.py:79-80` (PROCESSING не retryable); `domain/processing/state_machine.py:24-27`; `docker-compose.yml:105-119` (нет stop_grace_period → SIGKILL через 10s); RQ 3.0 internals (проверено): StartedJobRegistry.cleanup retry'ит abandoned jobs (heartbeat TTL ≤90s, maintenance 600s), НО при exhausted retries (3 краша) job уходит в FailedJobRegistry и DB-строка остаётся PROCESSING навсегда; Redis RDB-only persistence теряет очередь при краше.
- **Сценарий:** deploy/OOM во время видео-job → PROCESSING; `POST /retry` → 409; недокументированный обход cancel→retry (небезопасен без fencing, REL-3).
- **Последствия:** frozen job'ы, операторский тупик.
- **Исправление:** stale-sweeper (worker startup + периодика): PROCESSING/QUEUED с `updated_at < now() - (rq_job_timeout+120)` и мёртвым RQ-исполнением → FAILED(`stale_processing`/`stale_queued`); API retry допускает stale PROCESSING (безопасно с fencing); `stop_grace_period` worker; runbook cancel→retry в troubleshooting.
- **Тест:** integration: PROCESSING с updated_at=now()-2h → sweeper → FAILED → retry → resume без переобработки PROCESSED кадров.

### REL-7 — MEDIUM — retry_job orphan'ит QUEUED при отказе enqueue (асимметрия с create)
- **Файлы:** `backend/app/application/services/jobs.py:88-89` (commit QUEUED, затем enqueue БЕЗ try/except) vs `:56-64` (create компенсирует → FAILED queue_unavailable).
- **Сценарий:** Redis down во время retry → job навсегда QUEUED без RQ-job; QUEUED не retryable → тупик (обход cancel→retry).
- **Исправление:** зеркальная компенсация в retry_job; stale-QUEUED в sweeper.
- **Тест:** queue stub raises → POST retry → FAILED queue_unavailable.

### ARCH-6 — HIGH — FK CASCADE chain может стереть append-only историю review
- **Файлы:** `migrations/versions/0001_initial.py:276` (observations.job_id CASCADE), `:164` (jobs.upload_id CASCADE), `:350-351` (reviews CASCADE), `:374-375` (training_examples CASCADE), `:332` (defect_observations CASCADE).
- **Сценарий:** один `DELETE FROM processing_jobs` (или будущий cleanup-endpoint) каскадно уничтожает observations → reviews + training_examples. AGENTS §3/§8: Review/AuditLog append-only. Сегодня latent (нет delete-endpoints job'ов), но схема делает уничтожение истории одной SQL-командой.
- **Последствия:** безвозвратная потеря human-verified истории.
- **Исправление:** миграция 0002: RESTRICT на observations.processing_job_id, reviews.observation_id/defect_id, training_examples.observation_id/review_id.
- **Тест:** integration: job+observation+review → DELETE job → FK violation; roundtrip миграции.

---

## 2. P1 — критично для надёжности и корректности

### API-2 — HIGH — OpenAPI 422 декларирует HTTPValidationError, реально отдаётся error envelope
- **Файлы:** все роутеры (авто-422 FastAPI); `backend/app/api/errors.py:40-53` (реальный `{"error":...}`); проверено интроспекцией openapi().
- **Последствия:** сгенерированные клиенты парсят 422 неверно на всех 40 операциях.
- **Исправление:** custom APIRoute: замена default-422 на существующий `ErrorResponse` (schemas/common.py:25-26, сейчас мёртвый).
- **Тест:** contract: responses["422"] всех операций == ErrorResponse.

### API-3 — HIGH — Error responses не декларированы нигде
- **Файлы:** grep `responses=` по app/ → 0; runtime отдаёт 401/403/404/409/429(+Retry-After)/500/502/503/504 (`core/exceptions.py:24-103`).
- **Исправление:** shared responses dict через custom route class; per-endpoint 409/503.
- **Тест:** snapshot декларированных кодов per operation.

### API-1 — HIGH — 19/46 операций без response-схем; exports декларированы как application/json
- **Файлы:** analytics.py:12,17,22; assets.py:77-93 (nearby); map.py:17,31,45,64; uploads.py:42-83,122-127; jobs.py:21-42; reviews.py:24-52; exports.py:35,68,97; files.py:17; health.py:16,50,61 (интроспекция: `{}` или `{type:object,additionalProperties:true}`).
- **Исправление:** Pydantic-модели GeoJSON FeatureCollection (generic properties), Analytics*, Nearby*, UploadCreateResponse (уже существует, не подключён), binary media types для exports/files, health-модели; 200+201 truth (API-4).
- **Тест:** contract: каждый 2xx non-empty schema; exports media types != json.

### API-5 — MEDIUM — PATCH semantics сломаны (presence vs non-None)
- **Файлы:** `backend/app/schemas/assets.py:64-77` (`_not_empty` проверяет is not None, пропускает priority_override_reason).
- **Сценарий (воспроизведено):** PATCH `{"priority_override_reason":"x"}` → 422; PATCH `{"priority_override":null}` (clear) → 422; clear работает только piggyback; stale reason не очищается.
- **Исправление:** валидатор по `model_fields_set`; clear override очищает reason; документировать.
- **Тест:** unit/API: reason-only, override-clear-only, stale reason.

### API-6 / SEC-9 — MEDIUM — Idempotency-Key: >128 → 500 с потерей upload; глобальный job-key
- **Файлы:** `api/v1/uploads.py:52`, `jobs.py:27`, `reviews.py:30` (без max_length); `models/idempotency.py:16` String(128); `services/idempotency.py:27-34` (ловит только IntegrityError, DataError escapes); `models/job.py:64` (unique глобальный), `repos/jobs.py:23-25` (lookup без user scope).
- **Сценарий:** 129-char key → DataError → 500, upload откатывается; user B с ключом A получает job A (cross-user replay/squatting).
- **Исправление:** Header max_length=128 → 422; job-key scoped `(idempotency_key, upload_id)` (миграция 0002); concurrent same-key → catch IntegrityError → re-fetch replay.
- **Тест:** API 129-char → 422 без строки; two users one key →各自 job; gather race → один job.

### API-7 — MEDIUM — Replay игнорирует payload; обещанный 409 idempotency_conflict не возникает
- **Файлы:** `api/v1/idempotency.py:23-29`; `core/exceptions.py:65-66` (IdempotencyConflictError мёртвый); `docs/integrations/frontend-contract.md:66` (обещает 409).
- **Исправление:** request_hash в IdempotencyRecord (миграция 0002): uploads=checksum, jobs/reviews=sha256(body); mismatch → 409.
- **Тест:** replay с другим body → 409.

### API-8 — MEDIUM — Replay возвращает протухшие presigned URLs
- **Файлы:** `api/v1/uploads.py:36,75-78` (URL в кэшированном body); TTL 3600s; `models/idempotency.py` (нет expiry).
- **Исправление:** кэшировать body без presigned_url, re-enrich при replay.
- **Тест:** replay после TTL → свежий URL.

### API-10 — MEDIUM — corrected_condition молча деградирует в unknown
- **Файлы:** `schemas/assets.py:154` (free string); `domain/observations/condition.py:61-65`; `services/reviews.py:85-96` (asset_type/defect_type валидируются, condition — нет).
- **Сценарий (воспроизведено):** `corrected_condition="totally_bogus"` → 201, asset.current_condition='unknown', bogus label в training examples.
- **Исправление:** валидация против CONDITION_ALIASES/CANONICAL_CONDITIONS → 422; vocabulary в schema description.
- **Тест:** unit/API unknown condition → 422.

### API-11 — MEDIUM — reviewed_at из будущего принимается
- **Файлы:** `schemas/assets.py:158`; `services/reviews.py:108,186` (→ history detected_at).
- **Исправление:** reject > now+skew (5 мин).
- **Тест:** API 2036 date → 422.

### API-12 — MEDIUM — Defect PATCH: нет матрицы переходов, null-semantics drift
- **Файлы:** `api/v1/defects.py:86-94` (is not None вместо exclude_unset; блокируется только REJECTED→RESOLVED; RESOLVED→OPEN молча разрешён; OPEN→RESOLVED без review; нет locking).
- **Исправление:** доменная матрица переходов (domain/defects/transitions.py), DefectService, exclude_unset, документировать матрицу в OpenAPI.
- **Тест:** unit per transition; API RESOLVED→OPEN (reopen разрешён, documented), REJECTED→* → 422.

### API-15 — MEDIUM — map priority_band: str → 500 на invalid enum
- **Файлы:** `api/v1/map.py:23` (str вместо PriorityBand); `services/geospatial.py:62-63` (raw literal в SQL против native enum → PG 22P02 → 500, воспроизведено).
- **Исправление:** типизировать PriorityBand | None.
- **Тест:** API ?priority_band=BOGUS → 422.

### SEC-10 — LOW(→P1) — NaN accuracy_m в GPS metadata → перманентный 500 списков
- **Файлы:** `services/geolocation.py:49-55` (float() без finite-проверки); `pipeline.py:418`; Starlette JSONResponse allow_nan=False (проверено).
- **Сценарий:** metadata gps_track accuracy_m=NaN (json.loads принимает) → PG float8 NaN → каждая страница observations/assets с этой строкой → 500 для всех.
- **Исправление:** math.isfinite + диапазоны для accuracy_m/heading_deg/speed_mps в parse_track (invalid point).
- **Тест:** unit parse_track NaN/Inf; API списки остаются 200.

### SEC-6 — MEDIUM — Login rate limit по proxy IP → global lockout; нет per-account throttle
- **Файлы:** `api/v1/auth.py:17-19`; `core/ratelimit.py`; uvicorn forwarded_allow_ips default 127.0.0.1 (проверено).
- **Сценарий:** за nginx в другом контейнере все клиенты делят IP → 10 login/min глобально → lockout всех; с localhost-trusted proxy — XFF spoofing обход. Botnet → unlimited per account. Пароль от 1 символа.
- **Исправление:** per-username limiter (20/min); документировать FORWARDED_ALLOW_IPS; min password length для bootstrap.
- **Тест:** unit key-extraction; API 11-й login одного username с разных IP → 429.

### SEC-7 — MEDIUM — Нет logout/revocation; 60-мин неотрезываемые токены
- **Файлы:** `api/v1/auth.py` (только login/me); `core/security.py:31-57` (jti выдаётся, не проверяется).
- **Исправление:** POST /auth/logout + Redis jti denylist (TTL=exp), проверка в get_current_user.
- **Тест:** login→logout→token rejected; denylist TTL.

### SEC-8 — MEDIUM — Shared-registry gaps: cross-user delete, VIEWER presigned, checksum oracle
- **Файлы:** `api/v1/uploads.py:130-136` + `services/uploads.py:190-212` (delete без ownership); `api/v1/files.py:17-28` (любой ключ любому auth); `api/v1/uploads.py:33-39,112`, `serializers.py:36-58` (presigned всем ролям incl VIEWER на НЕанонимизированные кадры); `services/uploads.py:133-136` (dedup возвращает чужую запись с GPS metadata).
- **Контекст:** shared-read — явный дизайн (SECURITY.md:48-49), но ownership delete нигде не определён; privacy.md:54-56 сам рекомендует ограничить кадры OPERATOR+.
- **Исправление:** delete только uploader/ADMIN; presigned/image URLs только OPERATOR+; dedup чужого файла → нейтральный {id, created:false} без metadata/URL. Breaking pre-1.0 → docs+CHANGELOG.
- **Тест:** operator B не удаляет upload A (403); VIEWER без URLs; dedup без чужих metadata.

### SEC-15 / OPS-5 — MEDIUM — Redis down → 500 login/upload; fallback не работает
- **Файлы:** `core/ratelimit.py:20-31` (нет try/except; redis=None ветка только в тестах); `auth.py:17`, `uploads.py:54` (new limiter per request → in-memory fallback никогда не аккумулирует); SECURITY.md:99-100 обещает fallback.
- **Исправление:** catch RedisError → process-wide singleton in-memory limiter; unique zset members (uuid).
- **Тест:** failing Redis stub → fallback engages across checks; API Redis-down login работает.

### SEC-16 — LOW — Bootstrap-admin race между репликами
- **Файлы:** `services/auth.py:40-50` (count→insert без lock); unique username спасает от дубля, но вторая реплика crash-loop'ит.
- **Исправление:** INSERT ON CONFLICT DO NOTHING + re-read.
- **Тест:** concurrent bootstrap → один user, без исключений.

### SEC-17 — LOW — User enumeration по timing login
- **Файлы:** `services/auth.py:22-24` (unknown user пропускает ~100ms Argon2).
- **Исправление:** dummy verify против фиксированного hash.
- **Тест:** unit verify вызывается для unknown.

### SEC-18 — LOW — Presign expiry config игнорируется; PUT-presign capability
- **Файлы:** `infrastructure/storage/s3.py:102-112` (default 3600 перекрывает settings; method!=GET → put_object).
- **Исправление:** expires_seconds: int|None=None → settings; интерфейс GET-only.
- **Тест:** settings=60 → ExpiresIn=60; PUT недоступен.

### REL-2 — MEDIUM — RQ Retry инертен для pipeline-ошибок; poison retries на FAILED
- **Файлы:** `workers/tasks/processing.py:34-38`; `pipeline.py:135-219` (catch-all глотает даже JobTimeoutException → RQ FINISHED); `pipeline.py:109-115` (FAILED→PROCESSING invalid transition → RQ-retry FAILED job'а 3× raise → FailedJobRegistry noise).
- **Исправление:** run() резюмирует FAILED/PARTIALLY_COMPLETED (checkpoints безопасны); timeout-класс re-raise после FAILED для RQ takeover.
- **Тест:** integration RQ enqueue на FAILED строку → resume.

### REL-4 — MEDIUM — (job_id,detection_id) anchor неэффективен при re-inference
- **Файлы:** `schemas/ml.py:52` (request_id uuid4 per call); `pipeline.py:269-280,401-433` (job_frame_id никогда не пишется); mock seeds RNG по random request_id → новые detection_id; реальный HTTP ML亦然. Post-commit exception → PROCESSED→FAILED → re-inference → дубли observation того же кадра.
- **Исправление:** write-ahead raw ML response в job_frames.ml_response (миграция 0002) + reuse при re-run (provider-independent идемпотентность + экономия ML); deterministic request_id=uuid5(job_id,frame_index); job_frame_id wiring; never downgrade PROCESSED.
- **Тест:** stub random ids + post-commit exception → retry → 0 дублей.

### REL-8 — MEDIUM — finalize/cancel race; cancel→retry ломает cooperative cancel
- **Файлы:** `pipeline.py:619-640` (read→count→commit без lock; cancel между read и commit перезаписывается COMPLETED).
- **Исправление:** SELECT FOR UPDATE job row в finalize (или conditional UPDATE WHERE status<>CANCELLED).
- **Тест:** cancel внутри окна → финальный CANCELLED.

### REL-6 — MEDIUM — Timeout budget mismatch: 2000 кадров × 92s ≫ 1800s; S3 без deadlines
- **Файлы:** `config.py:32,47-49,80`; `http_provider.py` (3×30s+backoff ≈92s/кадр worst); `s3.py:34-38` (botocore default 60s, no overall deadline).
- **Исправление:** per-job timeout при enqueue = f(probe_frames, per-frame budget) с cap; explicit botocore connect/read timeouts.
- **Тест:** unit policy timeout ≥ frames×budget.

### REL-9 — MEDIUM — Dead-letter невидим; rq_job_id write-only
- **Файлы:** `services/jobs.py:65,90` (только запись); FailedJobRegistry не читается нигде.
- **Исправление:** GET /jobs/{id}/queue (ADMIN): RQ status/registry via rq_job_id; gauge failed registry на scrape.
- **Тест:** API endpoint reports registry membership.

### REL-10 / OPS-4 — MEDIUM — Метрики worker'а невидимы Prometheus в rq-mode
- **Файлы:** `core/metrics.py:7` (per-process REGISTRY); инкременты в worker процессе (`pipeline.py:194,197,259,328,642` и др.); /metrics только в API (`main.py:100-107`); worker без HTTP server. JOBS_ACTIVE gauge мёртв. JOB_DURATION не observe'ится на fail-путях.
- **Последствия:** весь processing-observability в production — нули на дашбордах.
- **Исправление:** prometheus_client.start_http_server(worker_metrics_port=9100) в worker.main; JOBS_ACTIVE + stale count на API scrape из БД; JOB_DURATION в _fail_job; compose/docs.
- **Тест:** scrape worker endpoint после job → counters > 0.

### OPS-1 — MEDIUM — Гонка миграций при multi-replica backend start
- **Файлы:** `docker-compose.yml:95` (alembic upgrade в command каждой реплики); alembic без advisory lock.
- **Исправление:** one-shot migrate service с pg_advisory_lock; backend depends_on migrate completed_successfully.
- **Тест:** два конкурентных alembic upgrade → оба exit 0.

### OPS-2 — MEDIUM — Shutdown не exception-safe
- **Файлы:** `main.py:62-68`; `workers/tasks/processing.py:28-31` (последовательные close без guard; один raise → остальные не закрыты).
- **Исправление:** AsyncExitStack / per-step try-except-log.
- **Тест:** stub ml.close raises → database.dispose всё равно вызван.

### OPS-3 — MEDIUM — In-flight jobs теряются при shutdown (10s grace)
- **Файлы:** `docker-compose.yml:105-119` (нет stop_grace_period); RQ warm shutdown не успевает за 10s.
- **Исправление:** stop_grace_period ≥ budget; sweeper (REL-1) как backstop; runbook.
- **Тест:** kill -9 worker mid-video → recovery ≤ threshold.

### GEO-3 — MEDIUM — CONFIRMED игнорирует GPS accuracy
- **Файлы:** `services/geolocation.py:25,82-92` (accuracy=1000m → CONFIRMED confidence 1.0, воспроизведено) → ложные NEW_ASSET при dedup радиусах 8-25m.
- **Исправление:** accuracy > gps_max_accuracy_m (50m) → ESTIMATED; None → CONFIRMED (backward compat).
- **Тест:** unit accuracy 1000 → not CONFIRMED.

### DEDUP-1 — MEDIUM — Candidate cap 10 может пропустить true match в плотной зоне
- **Файлы:** `repositories/assets.py:96-118` (limit=10); cabinets radius 8m.
- **Исправление:** dedup_max_candidates=50 (config).
- **Тест:** 12 assets, true match farthest + same-tracking → MATCHED.

### ARCH-4 — HIGH — Upload блокирует event loop (sync read/write до 2GB)
- **Файлы:** `services/uploads.py:109-118` (stream.read/tmp.write синхронно на loop); `api/v1/uploads.py:68`.
- **Последствия:** все конкурентные запросы (health/reviews/map) стоят на время upload'а.
- **Исправление:** await file.read(chunk) (Starlette offloads) или anyio.to_thread на spool-loop.
- **Тест:** concurrent slow upload + /health/live p99 < 100ms.

### ARCH-14 — MEDIUM — delete_upload удаляет storage-объект до commit
- **Файлы:** `services/uploads.py:204-212` (storage.delete → commit at request end; crash между → dangling row).
- **Исправление:** DB delete+commit сначала, storage потом (orphan object recoverable, orphan row — нет).
- **Тест:** forced commit failure → object intact.

### SEC-11 — LOW — CSV formula injection в exports
- **Файлы:** `services/exports.py:217-223` (без sanitization); attacker-controlled display_name/external_id через PATCH.
- **Исправление:** prefix `'` для ячеек, начинающихся с =,+,-,@,tab,CR.
- **Тест:** unit render escapes.

### SEC-12 — LOW — Prometheus cardinality explosion через 404 paths
- **Файлы:** `core/middleware.py:35-37` (unmatched route → raw path label).
- **Исправление:** константа "<unmatched>".
- **Тест:** unit middleware.

### SEC-13 — LOW — Нет security headers / TrustedHost; CORS wildcard+credentials hazard
- **Файлы:** `main.py:86-94`; проверено: Starlette отражает любой Origin при allow_origins=["*"]+credentials.
- **Исправление:** headers middleware (nosniff, XFO DENY, frame-ancestors, HSTS via proxy doc); config reject "*" при credentials.
- **Тест:** API headers present; settings wildcard → raise.

### SEC-14 — LOW — /health и job error_message раскрывают internal strings
- **Файлы:** `api/health.py:30,36,41,46` (str(exc)[:200] анонимам); `services/jobs.py:61`, `pipeline.py:214,657` (raw exception text всем VIEWER).
- **Исправление:** публично только status codes; детали в логи; error_message sanitize (codes only).
- **Тест:** API /health без detail; job failure только error_code.

### SEC-19 — LOW — Input-robustness cluster
- LIKE wildcards unescaped + search unbounded (`repos/uploads.py:41`, `assets.py:64`, `routes.py:33`); track point count unbounded (`schemas/routes.py:15-31`); X-Request-ID >64 → 500 на audited actions (`core/middleware.py:21` → `models/user.py:46`); любой ftyp brand = mp4 (HEIC проходит ingestion, `services/uploads.py:36,53-54`); files.py temp leak на ошибке (`api/v1/files.py:20-22`); local storage whole-file RAM (`local.py:45-54,86`); route finished_at<started_at принимается.
- **Исправления:** escape+cap 128; track ≤10k points; request-id truncate 64; ftyp brand allowlist; try/finally unlink; streaming copy; validator.
- **Тесты:** по одному на пункт.

### API-13 — MEDIUM — Unbounded списки: job frames (≤2000) и asset history (∞)
- **Файлы:** `repos/jobs.py:83-87`, `repos/misc.py:19-25`; `api/v1/jobs.py:85-91`, `assets.py:120-130` (bare arrays).
- **Исправление:** pagination envelope (breaking pre-1.0 → docs+tests+CHANGELOG); frames status filter.
- **Тест:** API >page_size → envelope.

### API-14 — MEDIUM — Unknown sort_by silent fallback; whitelists невидимы
- **Файлы:** `repos/base.py:43-45`; 7 list endpoints (free str).
- **Исправление:** per-resource Literal enums → 422 + OpenAPI enum.
- **Тест:** unknown sort → 422.

### API-20 — LOW — date_from>date_to принимается; date-field semantics vary
- **Исправление:** shared validator 422; документировать поле per resource.
- **Тест:** inverted range → 422.

### API-23 — LOW — Export silent 50k truncation; filter parity gap
- **Файлы:** `services/exports.py:26,98,186`; exports/observations без review_status/dedup_result.
- **Исправление:** X-Export-Truncated header; align filters; deterministic order.
- **Тест:** truncation header; parity.

### REL-11 — LOW — inline queue не заблокирован в production
- **Файлы:** `config.py:30,109-115`; `inline_queue.py`.
- **Исправление:** production+inline → raise.
- **Тест:** unit settings.

### REL-12 / OPS-12 — LOW — Temp leaks / orphan crops
- **Файлы:** `api/v1/files.py:20-27`; `pipeline.py:466-467` (crop key=random detection_id → orphan при rollback).
- **Исправление:** try/finally; deterministic crop keys (job,frame,ordinal).
- **Тест:** download failure → no tmp.

### REL-13 — LOW — total_frames estimate vs actual; progress=1.0 unconditional
- **Файлы:** `frames.py:23-38`; `pipeline.py:605,622-624,637`.
- **Исправление:** finalize total=processed+rejected+failed; upward reconcile при extraction > estimate (нужно для CHECK 0002).
- **Тест:** video test total == frame rows.

### DOC-3 — MEDIUM — test.sh flush'ит Redis db 0 (dev queue!)
- **Файлы:** `scripts/test.sh:30` (REDIS_URL /0) + `tests/conftest.py:89` (FLUSHDB).
- **Исправление:** default /15 в test.sh.
- **Тест:** scripted check.

### QA-1..7 — MEDIUM — Пробелы тестового покрытия (полный inventory в разделе 6)
Security regression, concurrency, infra-down, size limits, corrupted video, idempotency race, smoke/load — отсутствуют. Исправление: волна 3.

---

## 3. P2 — качество, производительность, сопровождаемость

### ARCH-1 — HIGH — N+1 observations: ≤200 StoredFile SELECT + 200 thread hops на страницу
- **Файлы:** `api/v1/serializers.py:50-57`; `observations.py:51-54`; `assets.py:153-156`.
- **Исправление:** batch `WHERE id = ANY(...)` + batch presign (один thread call).
- **Тест:** query-counter ≤4 SELECT на 100-row page.

### ARCH-2 — HIGH — N+1 defect observation_count (≤100 COUNT), дублировано в 2 роутерах
- **Файлы:** `api/v1/defects.py:49-53,70,105`; `assets.py:182-186`; set-based решение уже есть в `exports.py:153-165`.
- **Исправление:** один GROUP BY count по page ids; общий helper.
- **Тест:** query-counter ≤3.

### ARCH-3 / DEDUP-2 — HIGH — Dedup fan-out: 22-31 запрос/детекция (×10 candidates)
- **Файлы:** `services/deduplication.py:87-104` (latest_for_asset грузит полный Observation incl raw_model_payload; session.get(job); tracking select per candidate).
- **Исправление:** batch: DISTINCT ON latest observation per asset + join jobs (route_id) одним запросом; один EXISTS tracking по всем candidate ids; select только нужных колонок.
- **Тест:** ≤4 SELECT inside match при 10 candidates, decisions identical.

### PERF-1 — MEDIUM — Полный decode кадра на каждую детекцию
- **Файлы:** `pipeline.py:455` (_store_crop imdecode per detection) + quality grayscale decode.
- **Исправление:** один decode на кадр (lazy), ndarray в _store_crop; quality reuse.
- **Тест:** decode-count spy.

### ARCH-7 — MEDIUM — ProcessingPipeline god-class (660 строк, ~14 ответственностей)
- **Исправление:** extract FramePersistence + JobProgressTracker; run() оркестратор; существующие 9 pipeline-тестов unchanged.

### ARCH-8/9/API-17 — MEDIUM — Бизнес-логика/SQL в роутерах; reads bypass services (непоследовательно)
- **Файлы:** `defects.py:85-103` (state rule+audit), `routes.py:25-48` (WKT+ORM+ST_Length в роутере, без idempotency/audit); inventory reads в 8 роутерах.
- **Исправление:** DefectService, RouteService (+idempotency+audit); документировать read-via-repo pattern в AGENTS.

### ARCH-10 — MEDIUM — Дублирование: pagination envelope 9× (helper мёртв), observation_count 2×, CAS 2×, lonlat 2×, session_scope мёртв
- **Исправление:** использовать page_response/Page.to_dict; удалить session_scope; AssetService → update_with_version; общий defect serializer.

### ARCH-11 — MEDIUM — Worker создаёт engine/pool per task
- **Файлы:** `workers/tasks/processing.py:22,31`.
- **Исправление:** NullPool worker-side; inline reuse app.state.database.

### ARCH-15 — MEDIUM — Нет composite индексов под реальные filter+sort
- observations(asset_id,observed_at), observations(review_status,observed_at), defects(status,severity), defects(asset_id,defect_type,status), assets(asset_type,last_observed_at), jobs(status,created_at), defect_observations(observation_id) reverse.
- **Исправление:** миграция 0002. **Тест:** EXPLAIN/top-N scan.

### ARCH-16 — MEDIUM — Blocking CPU в async paths (cv2 inline, openpyxl exports во всех режимах)
- **Исправление:** anyio.to_thread для render; inline запрещён в prod (REL-11).

### ARCH-17 — MEDIUM — Local storage whole-file RAM (2GB ×2 на download)
- **Файлы:** `local.py:45-54,86`; `files.py:19-22` (metadata+download = double read).
- **Исправление:** shutil.copyfileobj streaming; checksum optional.
- **Тест:** 200MB download tracemalloc peak <10MB.

### ARCH-18 — MEDIUM — Analytics: unbounded route_stats join + 12 aggregates per request
- **Файлы:** `analytics.py:146-157,41-87`.
- **Исправление:** bbox/time-bound route_stats; consolidate counts.

### ARCH-19 — LOW — ~7 транзакций/кадр (stage/progress write amplification)
- **Исправление:** stage/progress внутри persistence транзакции; throttle.

### ARCH-20/PERF-3 — LOW — GeoJSON double serialization; LIMIT без ORDER BY (нестабильный subset)
- **Файлы:** `geospatial.py:29-33,64,108`; `serializers.py:64`.
- **Исправление:** mapping() напрямую (или ST_AsGeoJSON); deterministic order.

### ARCH-21 — LOW — paginate count over wide subquery
- **Исправление:** with_only_columns(func.count()).

### ARCH-22 — LOW — Redundant/unused indexes (8)
- ix_job_frames_job_id (covered by uq leftmost), created_at на users/stored_files/job_frames/idempotency_keys/audit_logs/asset_condition_history/training_examples (0 supporting queries, проверено).
- **Исправление:** drop в 0002; CreatedAtMixin index=False + explicit где нужно.

### ARCH-23 — LOW — Нет CHECK counters sum; retry не сбрасывает counters
- **Исправление:** CHECK processed+rejected+failed<=total (0002) + upward reconcile (REL-13); retry reset.

### ARCH-24 — LOW — Мёртвый код / speculative abstractions
- job_frame_id никогда не пишется (wiring в REL-4); EmbeddingSimilarityProvider в services (перенести в interfaces как documented extension); session_scope/count_for_asset/latest_for_observation/list_pending/mark_exported/get_by_external_id/get_by_key/JOBS_ACTIVE — удалить или подключить.

### ARCH-25 — LOW — Function-level imports noise (12 мест, циклов нет — проверено)
- **Исправление:** hoist кроме inline_queue/observability (legitimate).

### ARCH-26 — LOW — Lifespan leak при startup failure
- **Исправление:** AsyncExitStack (с OPS-2).

### ARCH-27 — LOW — get_settings cache stale edges в тестах
- **Исправление:** autouse cache_clear fixture.

### ARCH-28 — LOW — RateLimiter per-request instantiation (fallback ineffective)
- **Исправление:** singleton (с SEC-15).

### ARCH-30 — LOW — History: None→value priority не записывается; нет initial row
- **Исправление:** treat None→value as change.

### ARCH-32/PERF-5 — LOW — Export nondeterministic truncation; correlated subquery; peak ~150-250MB
- **Исправление:** order_by перед limit; window join вместо correlated; streaming — backlog.

### DEDUP-3 — LOW — same_route только по last observation
- **Исправление:** EXISTS over any observation job route.

### RISK-1/2 — LOW — REJECTED: stale condition при priority 0; is_physical=True для REJECTED
- **Исправление:** is_physical=False для REJECTED review; документировать semantics в ADR-0007.

### GEO-4 — LOW — Both-in-range swap undetectable (blind spot не документирован)
- **Исправление:** документировать в geospatial.md/ADR-0002.

### OPS-7/8/9/10/11 — LOW — dev reload storm (.venv), var ownership, s3-init || true, unpinned images, metrics_enabled/DEBUG dead
- **Исправления:** --reload-dir app; pre-create var; s3-init verify; pin tags; wire/remove settings; Dockerfile duplicate app install cleanup.

### CFG-3/4, DOC-1/2/4/5/6/7/9, SCALE-1 — LOW — Документация/конфиг drift
- .env.example неполон (25+ полей); testing.md stale CI note + false unit-infra claim; DEBUG dead; pip-audit --strict claim; export cap undocumented; multi-instance JWT doc.

---

## 4. P3 — косметика / Developer Experience (ядро Этапа 2)

- API-18: 0/46 descriptions, skeletal summaries, tags null/order accidental, no servers/contact/license, bearerFormat missing.
- API-19: 0 examples; enums без описаний; model-validator rules невидимы.
- API-22: job_id query vs processing_job_id field — документировать mapping.
- API-24: options dict мёртвый контракт; bbox/dedup_explanation/priority_factors additionalProperties:true; track maxItems невидим.
- API-25: overlapping endpoints не cross-referenced.
- DOC-9: minor doc mismatches.

---

## 5. VERIFIED-OK (с доказательствами)

1. **Домен чист:** 0 импортов fastapi/sqlalchemy/redis/boto3/cv2/httpx/infrastructure/application в app/domain/** (полный grep inventory).
2. **Циклов нет:** import app.main + workers + models OK; TYPE_CHECKING guards; function-level imports циклов не скрывают.
3. **ORM не утекает в API:** все ответы через schemas; relationship-поля в response-схемах отсутствуют.
4. **Lazy-load в async отсутствует:** exhaustive grep relationship traversals → 0 (serializers используют explicit session.get — N+1, но не MissingGreenlet). Рекомендация: lazy="raise" preventive.
5. **expire_on_commit=False осознан;** refresh после Core update корректен.
6. **Сессии не шарятся между tasks/threads;** sync boto/redis offloaded.
7. **create_review атомарен** (flush-only + commit at request end; idempotency record в той же транзакции); append-only соблюдён (0 UPDATE/DELETE путей Review/AuditLog).
8. **IdempotencyService.save begin_nested корректен** (SAVEPOINT изолирует unique violation).
9. **Покадровая персистенция атомарна** (StoredFile+observations+Asset/Defect+JobFrame — один commit); crash до commit → ничего; rerun идемпотентен (тест test_rerun_is_idempotent).
10. **History previous-values корректны** (record до мутации во всех 3 путях).
11. **Optimistic locking операторского PATCH работает** (CAS RETURNING + 409; тесты).
12. **ML contract v1.0 enforced** (Literal, extra=forbid, unique ids, bbox re-check, retry только timeout/5xx, error taxonomy, empty valid).
13. **PostGIS корректен:** geography ST_DWithin/ST_Distance, GiST (EXPLAIN: bbox использует ix_assets_location даже на 17 строках; candidate lookup на масштабе пойдёт через && expansion), lon/lat везде (проверено включая seed и тесты), SRID 4326, ST_Length метры.
14. **NaN/Inf отклоняются** на domain-уровне и Pydantic ge/le (воспроизведено для lon/lat/bbox/confidence).
15. **Миграционная дисциплина:** enums checkfirst+create_type=False, полный downgrade, naming convention, tz-aware map, 0 create_all.
16. **RBAC консистентен:** все мутации OperatorOrAdmin, reads CurrentUser; Argon2id OWASP-параметры (проверено эмпирически t=3,m=64MiB,p=4); JWT pinned algorithms+require exp/sub+type; role из БД не из токена; production empty-secret refuse.
17. **SQL-инъекций нет** (bind params everywhere; text() только SELECT 1; WKT из validated floats).
18. **sort whitelist enforced;** page_size ≤100 везде + clamp backstop.
19. **Filename sanitization robust;** magic bytes + RIFF subchecks + declared↔actual cross-check; empty rejected; text/html не может быть stored; downloads attachment.
20. **Path traversal + symlink escape закрыты** (safe_join resolve+is_relative_to); S3 bucket-scoped.
21. **SSRF нет** (httpx только ML provider, env-only base URL; сервер не fetch'ит user URLs).
22. **Unsafe deserialization в app коде нет** (0 pickle/yaml.load/eval; RQ pickle — trust boundary Redis, см. SEC-4).
23. **Error envelopes не leak'ают internals** (IntegrityError generic, unhandled generic+log, validation без input values).
24. **Секретов в логах/audit нет** (30 logger calls проверены; redaction processor; access log без query strings; bootstrap audit без password_hash).
25. **.env никогда не коммитился** (git log --all проверен); hardcoded secrets нет.
26. **Privacy честный** (NOT_APPLIED везде, 0 путей APPLIED без обработки).
27. **No fabricated GPS** (UNAVAILABLE+reason; DB CHECK location↔status; тест).
28. **AMBIGUOUS/POSSIBLE_MATCH не сливаются** (asset только NEW_ASSET/MATCHED; policy margin 0.10; explanation машиночитаемый персистится).
29. **Risk formula/NEEDS_REVIEW/override/REJECTED соответствуют ADR-0007;** policy version персистится.
30. **RQ 3.0:** atomic dequeue (lpop), abandoned-job recovery существует (heartbeat TTL ≤90s), warm shutdown, scheduler для retry intervals — проверено по internals.
31. **Redis pools bounded** (max_connections=100 в redis-py 8.1, не 2^31); один async client на app.
32. **Compose валиден** (config -q base+dev); Dockerfile multi-stage/non-root/uv не в runtime/OpenCV 5.0 libs достаточны (readelf проверен); .dockerignore корректен.
33. **CI механика корректна** (предсказание PASS: setup-uv inputs, lock committed, marker quoting, services health, localstack S3 env, conftest DB ordering, coverage path, docker context) — НО запуск на GitHub не верифицирован (API 404, нет доступа токена).
34. **OpenAPI 3.1.0; drift сегодня отсутствует** (committed == live, интроспекция); multipart схема документирована; Idempotency-Key header в OpenAPI присутствует.
35. **Route ordering safe** (/assets/nearby до /{id}); DELETE 204 корректен; POST /routes 201.
36. **262 теста = 108/35/83/36** (collect-only подтверждён); unit автономны (conftest skip для unit marker).
37. **OTel post-hoc instrumentation валиден** (до startup).
38. **pre-commit config консистентен** с Makefile.

---

## 6. Test-gap inventory (волна 3 закрывает)

| Сценарий | Есть | Отсутствует |
|---|---|---|
| IDOR/cross-user | — (shared-read by design) | ownership delete, VIEWER gating, dedup oracle |
| Role matrix | 2 viewer case | полный role×endpoint incl SERVICE |
| JWT tamper/expiry | expiry/garbage/unknown-user | signature tamper, alg-none, role-claim escalation, logout denylist |
| Path traversal API | unit/storage | GET /files/../ API |
| MIME spoof API | YES | — |
| Rate limit API | unit only | 429+Retry-After, Redis limiter, Redis-down fallback, per-username |
| Worker crash/stale | — | kill-mid-job, sweeper, fencing |
| Concurrent jobs upload | — | 409 guard test |
| Concurrent PATCH | sequential 409 | gather race |
| Concurrent dedup | sequential 6 | parallel same-object → 1 asset |
| Redis/PG/S3 down | pipeline storage-down | API-level, queue_unavailable |
| ML timeout | pipeline+unit http | — (достаточно) |
| Max size reject | enforcement | test small limit |
| Corrupted video | image only | video |
| Export cap | 4 tests | truncation signal, large selection |
| NaN/Inf API | range 422 | explicit payloads |
| Idempotency race | sequential replays | gather race, fingerprint 409 |
| Smoke/load | — | scripts/smoke.sh, load_smoke.py |
| Migration 0002 | — | up/down empty+populated |
| Body limits | — | 413 multipart/JSON pre-auth |
| Dimension bomb | — | reject before decode |

---

## 7. План исправлений (волны)

- **Волна 0 (лид):** этот документ; миграция 0002 (RESTRICT FK, active-upload unique, idempotency scope+hash, ml_response, composites, drop unused, counters CHECK); models sync; config (новые settings + production validator); domain (defect transitions, condition validator, history REJECTED).
- **Волна 1 (4 параллельных агента, непересекающиеся файлы):** Security (P0 SEC-1..5,8,11..19 + P1 auth), Reliability (REL-1..13, GEO-1/3, DEDUP-1/2/3, PERF-1/2, ARCH-4/11/14 worker-side), API-quality (API-1..15,20,23, ARCH-1/2/8/9/10/24/30/32, SEC-9/10 API-side), Docs-fix (DOC-*, .env.example, test.sh db15, backup scripts).
- **Интеграция (лид):** main.py wiring, pipeline декомпозиция (ARCH-7), полный прогон.
- **Волна 2:** OpenAPI Developer Portal (API-1/2/3/4/14/18/19/22/24/25 + Этап 2 целиком), Contracts tooling (drift/breaking/TS/contract tests/docs/api + integrations README).
- **Волна 3:** QA (все gaps раздела 6), DevOps (compose hardening SEC-4/OPS-1/3/7/8/9/10, worker metrics OPS-4, CI additions, ci_local.sh, backup/restore).
- **Финал:** полная верификация + отчёт.

Breaking-изменения pre-1.0 (docs+schemas+tests+CHANGELOG обязательны): frames/history pagination; VIEWER URL gating; neutral dedup; sort_by 422; compose default ports; idempotency fingerprint 409.

---

## 8. Статус исправлений (обновлено 2026-11-16, волны 0–3 завершены)

**Итог верификации:** 661 тест passed / 0 failed / 0 xfail; ruff check + format clean;
mypy clean (137 файлов); `scripts/ci_local.sh` — 12/12 PASS; smoke против живого стека
(RQ worker) — OK; load smoke: 530 запросов, 0 ошибок, p50 0.143s / p95 0.669s;
pip-audit --strict — уязвимостей нет; Swagger UI проверен в браузере (Authorize +
Try it out → реальный 200-ответ); worker :9100/metrics показывает pipeline-счётчики
после job (multiprocess-режим).

### P0 — все FIXED
| ID | Исправление | Доказательство |
|---|---|---|
| SEC-1/2 | BodyLimitMiddleware (413 до auth, Content-Length + streaming count) | tests/api/test_security_regression.py (413 JSON/multipart), unit middleware |
| SEC-3+CFG-1 | production-валидатор placeholders/length/S3/inline/CORS; .env.example пустые секреты | tests/unit/test_security_hardening.py + config tests |
| SEC-4 | базовый compose без infra host-портов; dev-override явно; redis appendonly | compose config audit (DevOps), ci_local infra step |
| SEC-5+PERF-2 | dimension probe до decode, 64MP/8192 лимиты, downscale 4096, OPENCV_IO_MAX_IMAGE_PIXELS | unit probe tests (decode-spy), test_reliability_hardening.py |
| GEO-2 | S3_PUBLIC_ENDPOINT_URL + отдельный presign-client | unit presign host test; smoke в Docker (URL localhost:9000) |
| GEO-1 | UTC-нормализация naive timestamps (parse_track/_resolve_start) | unit naive/mixed tests; integration |
| REL-5+ARCH-12 | partial unique active-upload + 409; grid advisory xact lock; version bump в pipeline/reviews | test_concurrency.py (2 jobs → 409; concurrent dedup → 1 asset), test_reliability_integration.py |
| REL-3 | pg_try_advisory_lock fencing на всё run(); PROCESSED→FAILED запрещён | test_reliability_integration.py fencing |
| REL-1/7 | stale-sweeper (startup+600s), stale PROCESSING retry, retry-компенсация queue_unavailable | test_failure_modes.py, test_reliability_integration.py sweeper |
| ARCH-6 | миграция 0002: RESTRICT на observations.job_id, reviews.*, training_examples.* | test_queue_migrations roundtrip; FK violation test |

### P1 — все FIXED
API-1/2/3/4 (response-схемы всех 47 операций, ErrorResponse на 422, декларированные
ошибки, 200/201 truth) — tests/contracts/test_openapi_contract.py (29 тестов);
API-5 (model_fields_set), API-6/7/8/9 (max_length, fingerprint 409, replay URL refresh,
scoped job-key), API-10/11 (condition vocabulary, reviewed_at bound), API-12 (матрица
переходов DefectService), API-13 (frames/history pagination), API-14 (sort Literal),
API-15 (typed PriorityBand), API-20 (date-range 422) — test_api_semantics*.py;
SEC-6 (per-username throttle), SEC-7 (logout+jti denylist), SEC-8 (ownership delete,
VIEWER gating, redacted dedup), SEC-15 (fallback singleton), SEC-16 (ON CONFLICT
bootstrap), SEC-17 (dummy verify), SEC-18 (presign expiry/GET-only), SEC-10 (finite
GPS metadata), SEC-11 (CSV escaping), SEC-12 ("<unmatched>"), SEC-13 (headers),
SEC-14 (sanitized errors), SEC-19 cluster — test_security_regression.py + unit;
REL-2 (resume FAILED/PARTIALLY), REL-4 (write-ahead ml_response + deterministic
request_id + job_frame_id), REL-8 (finalize FOR UPDATE), REL-6 (botocore timeouts;
budget-documentation + sweeper recovery), REL-9 (rq_job_id liveness в sweeper;
FailedJobRegistry visibility через sweeper logs), REL-10/OPS-4 (worker metrics
multiprocess — проверено curl :9100 после job), REL-11 (production inline guard),
REL-12 (deterministic crop keys, files temp finally), REL-13 (total reconcile);
GEO-3 (accuracy gate), DEDUP-1/2/3 (cap 50, batch ≤4 запроса, same_route EXISTS);
ARCH-4 (async read_chunk), ARCH-14 (DB-first delete + post-commit storage);
OPS-1 (migrate advisory lock — 2 concurrent → exit 0), OPS-2 (AsyncExitStack),
OPS-3 (stop_grace_period 300s + sweeper); DOC-3 (test.sh db15).

### P2 — FIXED (производительность/качество)
ARCH-1/2/3 (batch serializers/counts/dedup evidence — query-counter тесты ≤4 SELECT),
ARCH-7 (pipeline → оркестратор + FramePersistence + JobProgressTracker),
ARCH-8/9/10 (DefectService/RouteService, page_dict, единый CAS/lonlat),
ARCH-11 (NullPool worker, inline reuse), ARCH-15 (6 composite + reverse index, 0002),
ARCH-16 (export render остаётся sync в request — допустимо MVP, inline запрещён prod;
отмечено как остаточное), ARCH-17 (local streaming), ARCH-18 (overview consolidation,
route_stats bbox-bound), ARCH-19 (progress throttle 5 кадров), ARCH-20/PERF-3
(mapping напрямую, deterministic order), ARCH-21 (maintain_column_froms count),
ARCH-22 (drop 8 индексов, 0002), ARCH-23 (frames_sum CHECK + retry reset),
ARCH-24 (dead code удалён/job_frame_id wired/embeddings port в interfaces),
ARCH-25 (imports hoisted), ARCH-26 (AsyncExitStack), ARCH-27 (conftest fixture
resolution fix), ARCH-28 (singleton), ARCH-30 (None→value history),
ARCH-32 (export order), PERF-1 (single decode), DEDUP-3, RISK-1/2 (documented +
is_physical=False), GEO-4 (documented), OPS-7/8/9/10/11, CFG-3/4, DOC-1..9, SCALE-1.

### P3 — FIXED
API-18/19/22/24/25 (описания/примеры/320+ example blocks/enum docstrings/
cross-references) — Developer Portal; DOC-9.

### Остаточные ограничения (не блокируют, задокументированы)
- ARCH-16: export render синхронный в request (50k cap, ~150-250MB peak) — streaming
  через server-side cursor отложен до реальных объёмов.
- PERF-5/PERF-6: export memory и coverage expression-scan — backlog с триггерами масштаба.
- Presign batching (один thread-call на страницу) — отложен (per-key await, DB N+1 устранён).
- GitHub CI не запускался из этой среды (нет API-доступа к репозиторию); локальный
  эквивалент ci_local.sh — 12/12 PASS.
- HTTP ML против живого сервиса, OTel с реальным collector — не проверено (сервисов нет).
- Реальные данные МГТС: калибровка порогов dedup/risk/quality, финальная таксономия.
