# Поток данных — pipeline обработки

Полный конвейер от загрузки файла до завершённого job:

```
UPLOAD → VALIDATION → STORAGE → JOB → FRAME EXTRACTION → QUALITY GATE →
PRIVACY FILTER → INFERENCE → NORMALIZATION → TRACKING → GEOLOCATION →
DEDUPLICATION → RISK SCORING → PERSISTENCE → COMPLETED
```

Первые четыре стадии (UPLOAD…JOB) выполняются **синхронно в API-процессе** при
загрузке файла и создании job. Стадии FRAME EXTRACTION…COMPLETED выполняются
**асинхронно в воркере** внутри `ProcessingPipeline.run`
(`backend/app/application/use_cases/processing/pipeline.py`).

> Замечание о `current_stage`. Enum `ProcessingStage` (`domain/enums.py`) содержит
> все стадии начиная с `VALIDATION`. Однако pipeline фактически выставляет
> `current_stage` только в трёх точках: `FRAME_EXTRACTION` (старт),
> `PERSISTENCE` (после каждого кадра, `_update_progress`), `COMPLETED` (финал).
> Промежуточные стадии (QUALITY_GATE…RISK_SCORING) выполняются внутри обработки
> кадра, но отдельное значение `current_stage` для них не пишется. UPLOAD и JOB
> в enum отсутствуют — это стадии до появления job.

## Стадии

### 1. UPLOAD
- **Где:** `api/v1/uploads.py::create_upload` → `application/services/uploads.py::UploadService.create_upload`.
- **Что:** приём multipart (`file`, `route_id`, `metadata` JSON, заголовок `Idempotency-Key`).
  Rate limit по пользователю (`rate_limit_upload_per_minute`). Обёртка `idempotent_post`
  (`api/v1/idempotency.py`) обеспечивает replay сохранённого ответа.
- **Результат:** запись `Upload` + `StoredFile(kind=ORIGINAL)`, presigned-URL в ответе.

### 2. VALIDATION
- **Где:** `services/uploads.py` (`_validate_declared`, `sniff_media_type`, `sanitize_filename`).
- **Что:**
  - расширение и заявленный MIME должны соответствовать спискам из `Settings`;
  - потоковое чтение чанками по 1 MiB, контроль `max_upload_size_bytes` (по умолчанию 2 GiB);
  - проверка magic-байтов (JPEG/PNG/WEBP/WebM/AVI/MP4/QuickTime) и совпадения
    фактического MIME с заявленным;
  - пустой файл отклоняется;
  - вычисляется SHA-256.
- **Ошибки:** `ValidationAppError` (HTTP 422).

### 3. STORAGE
- **Где:** `services/uploads.py` → `ObjectStorage.upload_file` (`infrastructure/storage/s3.py`).
- **Что:** **checksum-дедупликация** — если `Upload` с таким `checksum_sha256` уже есть,
  возвращается существующий (`created=False`, HTTP 200), файл повторно не грузится.
  Иначе объект кладётся по ключу `uploads/{upload_id}/{safe_name}`, создаются
  `Upload` и `StoredFile`, пишется audit (`AuditAction.CREATE`).
- **Инвариант:** бинарное содержимое **никогда** не хранится в PostgreSQL — только метаданные.

### 4. JOB
- **Где:** `api/v1/jobs.py::create_job` → `services/jobs.py::JobService.create_job`.
- **Что:** создание `ProcessingJob(status=PENDING)`, переход `PENDING→QUEUED`
  (валидируется `assert_transition`), постановка в очередь `JobQueue.enqueue_processing`.
  `idempotency_key` job уникален (`uq_processing_jobs_idempotency_key`).
  При недоступности очереди job помечается `FAILED` с `error_code=queue_unavailable`.
- **Очередь:** `RQJobQueue` (`infrastructure/queue/rq_queue.py`) ставит задачу по
  import-path `app.workers.tasks.processing.process_upload_task` (API не импортирует
  код воркера). Retry RQ: `Retry(max=3, interval=[10,30,60])`, timeout 1800 c.

### 5. FRAME EXTRACTION
- **Где:** `pipeline.py::run` → `use_cases/processing/frames.py` (`probe_frame_count`, `extract_frames`).
- **Что:** файл скачивается из хранилища во временный каталог (`download_to_file`).
  Изображение → 1 кадр. Видео → кадры с шагом `processing_frame_interval_seconds`
  (по умолчанию 1 c), не более `processing_max_frames` (2000); fps fallback 25.
  `observed_at` кадра = `capture_started_at` из метаданных (или `upload.created_at`)
  + смещение по времени. `total_frames` записывается в job.
- **Ошибки:** нечитаемый файл → `ValidationAppError` → job `FAILED`.

### 6. QUALITY GATE
- **Где:** `use_cases/processing/quality.py::HeuristicQualityGate.evaluate`.
- **Что:** эвристики OpenCV — `low_resolution` (<320×240), `blur` (дисперсия
  Лапласиана <60), `overexposure` (mean>245), `underexposure` (mean<10),
  `undecodable_frame`. При `quality_gate_enabled=False` всё проходит.
- **Результат:** `REJECT` → кадр получает `FrameStatus.REJECTED` с `reject_reason`,
  инкремент метрики `pipeline_frames_rejected_total{reason}`. Дальше кадр не идёт.

### 7. PRIVACY FILTER
- **Где:** `use_cases/processing/privacy.py::NoopPrivacyFilter.process`.
- **Что:** MVP — no-op: кадр проходит без изменений, статус `AnonymizationStatus.NOT_APPLIED`.
  Система **не заявляет** анонимизацию, которая не выполнялась. Кадр (после фильтра)
  грузится в хранилище по ключу `frames/{job_id}/{index:06d}.jpg`, создаётся
  `StoredFile(kind=FRAME)` с `anonymization_status` и метриками качества.

### 8. INFERENCE
- **Где:** `pipeline.py::_process_frame` → `MLProvider.infer_image`
  (`infrastructure/ml/mock_provider.py` / `http_provider.py`).
- **Что:** формируется `MLInferenceRequest` (`schemas/ml.py`, `schema_version 1.0`):
  ссылка на кадр (`storage_key`, width, height) + метаданные (lon/lat, heading, speed,
  route_id, frame_index). HTTP-провайдер валидирует ответ по контракту, проверяет
  `request_id` и границы bbox, ретраит таймауты/5xx (1 + `ml_http_retries` попыток,
  экспоненциальный backoff + jitter); 4xx не ретраятся.
- **Ошибки:** `MLProviderError` → кадр `FrameStatus.FAILED` с `error_code`, job продолжается.

### 9. NORMALIZATION
- **Где:** `pipeline.py::_persist_detection` → `domain/observations/condition.py`.
- **Что:** `normalize_condition` приводит ML-метку к каноническому словарю
  (алиасы → `ok/damaged/missing_cover/...`, неизвестное → `unknown`).
  Если severity не задан ML и condition не `ok/unknown`, берётся
  `default_severity_for_condition`. Валидируется `PixelBBox` в границах кадра.

### 10. TRACKING
- **Где:** `pipeline.py` (извлечение `tracking_id` из `detection.attributes`),
  `services/deduplication.py::_match_by_tracking`.
- **Что:** `tracking_id` сохраняется в `Observation.tracking_id`. При отсутствии GPS
  дедупликация опирается на tracking: предыдущее наблюдение того же job с тем же
  `tracking_id` и `object_type`, уже привязанное к активу, даёт `MATCHED` (score 1.0).

### 11. GEOLOCATION
- **Где:** `services/geolocation.py::GeolocationService.locate` (вызывается в `_process_frame`).
- **Что:** по GPS-треку из `upload.metadata['gps_track']`:
  - ближайшая точка с зазором ≤2 c → `CONFIRMED` (source GPS, confidence 1.0);
  - зазор ≤10 c → `ESTIMATED` (линейная интерполяция, confidence 0.6/0.4);
  - зазор >10 c или трека нет → `UNAVAILABLE` (без координат).
- **Политика:** координаты **не выдумываются**. Инвариант `GeoObservation`:
  CONFIRMED/ESTIMATED обязаны иметь точку; UNAVAILABLE/INVALID — не иметь.

### 12. DEDUPLICATION
- **Где:** `services/deduplication.py::DeduplicationService.match` →
  `domain/deduplication/policy.py::decide`.
- **Что:** кандидаты из PostGIS (`AssetRepository.find_candidates`: `ST_DWithin` +
  `ST_Distance`, GiST, только `ACTIVE`, тот же `asset_type`, радиус из таксономии).
  Для каждого кандидата собираются свидетельства (distance, hours_since_last_observation,
  same_route, same_tracking_id) и считается взвешенный score.
  Веса: spatial 0.55, type 0.20, temporal 0.05, context 0.15, visual 0.05.
  Пороги (из `Settings`): match **0.70**, possible **0.45**; радиус по умолчанию 15 м,
  окно 2 ч. Два сильных кандидата с разницей <0.10 → `AMBIGUOUS` (без авто-слияния).
- **Результат:** `MATCHED` (привязка к активу), `NEW_ASSET` (создание актива),
  `POSSIBLE_MATCH`/`AMBIGUOUS` — актив не создаётся и не сливается, observation
  остаётся **без asset_id** (кандидат сохраняется в `dedup_explanation`), требуется review.
  Решение и `explanation` сохраняются в observation.

### 13. RISK SCORING
- **Где:** `services/risk.py::RiskScoringService.assess` → `domain/risk/scoring.py::assess_risk`.
- **Что:** `priority = 100 * severity_norm * impact_factor * (0.5 + 0.5*confidence)`.
  Bands: HIGH ≥70, MEDIUM ≥40, иначе LOW; `NEEDS_REVIEW` при низкой confidence (<0.6),
  неизвестной severity или dedup `POSSIBLE_MATCH/AMBIGUOUS` (если нет review).
  `REJECTED` review → LOW, priority 0. `manual_override` имеет precedence.
  Результат применяется к активу (`apply_to_asset`) и пишется в историю.

### 14. PERSISTENCE
- **Где:** `pipeline.py::_persist_detection`, `_update_asset_from_observation`,
  `_upsert_defect`, `_store_crop`, `_record_frame`.
- **Что:** в одной транзакции на кадр:
  - создаётся `Observation` (с dedup-решением, effective-полями, raw_model_payload);
  - crop детекции сохраняется как `StoredFile(kind=CROP)` (`crops/{job_id}/{detection_id}.jpg`);
  - при наличии актива: обновляются first/last_observed_at, current_condition/severity,
    location (если улучшается), risk; пишется `AssetConditionHistory`;
  - upsert `Defect` по `defect_type_for_condition` (max severity, link observation);
  - кадр фиксируется в `JobFrame(status=PROCESSED)`.

### 15. COMPLETED
- **Где:** `pipeline.py::_finalize`.
- **Что:** пересчёт счётчиков кадров из `job_frames`, итоговый статус, `progress=1.0`,
  `current_stage=COMPLETED`, `finished_at`, метрика `processing_job_duration_seconds`.

## Обработка ошибок по кадрам

- Каждый кадр обрабатывается в `try/except` (`pipeline.py::run`). Любое исключение
  → `FrameStatus.FAILED`, запись `JobFrame` с `error_code=frame_processing_error`,
  метрика `pipeline_frames_failed_total`. **Job не прерывается** — следующие кадры продолжаются.
- Ошибка ML (`MLProviderError`) → кадр `FAILED` с кодом ошибки ML, job продолжается.
- Отклонение quality gate → кадр `REJECTED` (не ошибка).
- Фатальные ошибки вне цикла (скачивание, извлечение кадров) → job `FAILED`
  (`_fail_job`, `error_code`/`error_message`, `finished_at`).

## Частичное завершение (partial completion)

Логика `_finalize`:
- `failed_frames == 0` → `COMPLETED`;
- есть failed, но `processed_frames > 0` или `rejected_frames > 0` →
  `PARTIALLY_COMPLETED` (`error_code=partial_frame_failures`);
- все кадры failed → `FAILED` (`error_code=all_frames_failed`);
- отмена → `CANCELLED`.

`PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED` допускают retry (`RETRYABLE_STATUSES`).

## Якоря идемпотентности

| Якорь | Constraint | Эффект |
|-------|-----------|--------|
| `job_frames` | `uq_job_frame_index` UNIQUE(`job_id`, `frame_index`) | один кадр — одна запись; повторный прогон пропускает уже `PROCESSED/REJECTED/SKIPPED` (`_process_frame`) |
| `observations` | `uq_observations_job_detection` partial UNIQUE(`processing_job_id`, `detection_id`) WHERE `detection_id IS NOT NULL` | повторная детекция не дублируется (`exists_by_job_detection` → skip) |
| `processing_jobs.idempotency_key` | `uq_processing_jobs_idempotency_key` | повторное создание job с тем же ключом возвращает существующий |
| `uploads.checksum_sha256` | `uq_uploads_checksum_sha256` | повторная загрузка того же файла не создаёт новый upload |
| `idempotency_keys` | `uq_idempotency_scope` UNIQUE(`key`, `user_id`, `endpoint`) | replay ответа для unsafe POST |

Повторный запуск job безопасен: терминальные `COMPLETED`/`CANCELLED` пропускаются
(`pipeline_skip_terminal`); `PROCESSING` может быть «перехвачен» воркером
(`pipeline_takeover_processing_job`); уже обработанные кадры и детекции не пересоздаются.

## Отслеживание прогресса

- `_update_progress` вызывается после каждого кадра: обновляет
  `processed_frames`, `rejected_frames`, `failed_frames`,
  `progress = min(1.0, done/total)`, `current_stage=PERSISTENCE`.
- Итоговые счётчики в `_finalize` перечитываются из `job_frames` (`count_by_status`).
- API: `GET /jobs/{id}` (статус/прогресс), `GET /jobs/{id}/frames` (покадрово).
- Метрики Prometheus: `pipeline_frames_processed_total`, `pipeline_frames_rejected_total{reason}`,
  `pipeline_frames_failed_total`, `pipeline_detections_total`, `deduplication_results_total{result}`,
  `processing_job_duration_seconds{status}`, `rq_queue_length`.

## Отмена (cancellation)

- `POST /jobs/{id}/cancel` → `JobService.cancel_job`: допустимо для
  `PENDING/QUEUED/PROCESSING` (`CANCELLABLE_STATUSES`), переход в `CANCELLED`.
- Воркер проверяет статус job **каждые 10 кадров** (`_CANCEL_CHECK_EVERY=10`);
  при `CANCELLED` цикл прерывается, `_finalize` фиксирует `CANCELLED`.
- `_update_progress` не перезаписывает прогресс отменённого job.
- `CANCELLED` допускает повторный запуск (retry → `QUEUED`).

## Связанные документы
- [Обзор системы](system-overview.md) · [Доменная модель](domain-model.md) ·
  [Sequence-диаграммы](sequence-diagrams.md) · [Схема БД](../database/schema.md)
