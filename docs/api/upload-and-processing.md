# Загрузка и обработка

Полный путь данных: `POST /uploads` (multipart) → `POST /jobs` → worker
(RQ) покадрово обрабатывает загрузку → наблюдения/активы/дефекты →
`GET /observations`, `/assets`, `/map/*`.

## 1. Загрузка файла (multipart)

```
POST /api/v1/uploads
Content-Type: multipart/form-data
Authorization: Bearer <token>   (роль OPERATOR / SERVICE / ADMIN)
Idempotency-Key: <uuid>        (опционально, рекомендуется)
```

| Часть | Тип | Обязательность | Описание |
|---|---|---|---|
| `file` | binary | да | Изображение или видео |
| `route_id` | uuid (form field) | нет | Привязка к маршруту объезда |
| `metadata` | string (JSON-объект) | нет | GPS-трек и время съёмки (ниже) |

Ответ: **201** — новая загрузка; **200** — дубликат по checksum
([upload-created.json](../../contracts/examples/api/upload-created.json)):

```json
{"upload": {"id": "…", "original_filename": "…", "storage_key": "uploads/{id}/{name}",
            "content_type": "image/jpeg", "file_size": 482317,
            "checksum_sha256": "…", "media_type": "IMAGE",
            "uploaded_by": "…", "route_id": "…", "metadata": {"…": "…"},
            "created_at": "…", "presigned_url": "http://…"},
 "created": true}
```

### Форматы и проверки содержимого

| Медиа | Расширения | MIME | Magic bytes |
|---|---|---|---|
| IMAGE | `.jpg`, `.jpeg`, `.png`, `.webp` | `image/jpeg`, `image/png`, `image/webp` | JPEG `FF D8 FF`, PNG-сигнатура, RIFF+`WEBP` |
| VIDEO | `.mp4`, `.avi`, `.mov`, `.webm` | `video/mp4`, `video/x-msvideo`, `video/quicktime`, `video/webm` | `ftyp` (бренды isom/mp42/qt и др.), RIFF+`AVI `, EBML |

Проверяются **все три** признака: расширение, declared MIME и magic bytes;
несоответствие любого → 422 `validation_error`. Пустой файл → 422.
Имя файла санитизируется (≤ 200 символов, безопасные символы).

### Лимиты размера (413 до аутентификации)

- Загрузка: `MAX_UPLOAD_SIZE_BYTES` = **2 GiB** (+ 1 MB multipart-overhead).
- JSON-тела (login/jobs/reviews/…): `MAX_JSON_BODY_BYTES` = **2 MiB**.
- Body-limit middleware отказывает **до auth и без полной буферизации**:
  по `Content-Length` заранее либо mid-stream при превышении → 413
  `payload_too_large` (единый error-конверт).

### metadata: GPS-трек

`metadata` — JSON-объект (строкой в form field). Ключевые поля:

```json
{
  "capture_started_at": "2026-11-15T12:00:00Z",
  "gps_track": [
    {
      "timestamp": "2026-11-15T12:00:00Z",
      "longitude": 37.6165,
      "latitude": 55.7554,
      "accuracy_m": 4.5,
      "heading_deg": 48.0,
      "speed_mps": 5.2
    }
  ]
}
```

| Поле точки | Тип | Ограничения |
|---|---|---|
| `timestamp` | ISO 8601 | обязателен; naive → UTC (assume-UTC) |
| `longitude` / `latitude` | float | обязательны, парой; WGS84-диапазоны |
| `accuracy_m` | float \| null | ≥ 0, конечное; > 50 м → статус ESTIMATED |
| `heading_deg` | float \| null | [0, 360) |
| `speed_mps` | float \| null | ≥ 0 |

- `capture_started_at` — опорное время съёмки: timestamp кадра =
  `capture_started_at + frame_index * PROCESSING_FRAME_INTERVAL_SECONDS`.
- Невалидные точки трека пропускаются (считаются), job не падает.
- **Без GPS объекты создаются со статусом `UNAVAILABLE`** — это штатный
  режим; координаты не выдумываются. Семантика статусов —
  [geospatial.md](geospatial.md).
- Невалидный JSON в `metadata` → 422.

### Checksum-дедупликация и redaction

SHA-256 содержимого уникален (`uploads.checksum_sha256 UNIQUE`):

- Повторная загрузка **того же файла тем же пользователем** (или ADMIN) →
  200, `created: false`, полная карточка существующей загрузки.
- Повторная загрузка чужого файла → 200, `created: false`, **redacted**-карточка
  ([upload-duplicate-redacted.json](../../contracts/examples/api/upload-duplicate-redacted.json)):
  `original_filename = "[redacted]"`, `storage_key = "[redacted]"`,
  `content_type = "application/octet-stream"`, `uploaded_by = null`,
  `route_id = null`, `metadata = {}`, `presigned_url = null`.
  Это защита от checksum-oracle: узнать чужой файл/GPS нельзя.

### Прочие операции с загрузками

- `GET /uploads` — фильтры `media_type`, `route_id`, `search`, `date_from/to`.
- `GET /uploads/{id}` — карточка (+ presigned_url для ролей с доступом к медиа).
- `DELETE /uploads/{id}` — **204**; только загрузивший или ADMIN (иначе 403);
  при наличии связанных jobs → 409 `conflict`. Объект в хранилище удаляется
  после commit транзакции.

## 2. Создание job

```
POST /api/v1/jobs
{"upload_id": "<uuid>", "route_id": "<uuid>?", "options": {}}
Idempotency-Key: <uuid>
```

- **201** — job создан; **200** — replay того же ключа с идентичным payload.
- `options` — зарезервировано (informational), не влияет на обработку.
- **Active-upload guard**: у загрузки может быть только один активный job
  (PENDING/QUEUED/PROCESSING). Повторное создание → 409 `conflict`
  ("Upload already has an active processing job").
- Идемпотентность: ключ scoped по пользователю и endpoint; replay с другим
  payload → 409 `idempotency_conflict`; длина ключа ≤ 128 (иначе 422).
- Обработка асинхронная: worker RQ (`QUEUE_MODE=rq`); в dev/test допустим
  `inline` (в production запрещён валидатором).

## 3. Жизненный цикл job

Статусы (`JobStatus`):

```
PENDING → QUEUED → PROCESSING → COMPLETED
                              ↘ PARTIALLY_COMPLETED
                              ↘ FAILED
                    (cancel)  → CANCELLED
```

| Статус | Смысл | Терминальный |
|---|---|---|
| `PENDING` | Создан, ещё не поставлен в очередь | нет |
| `QUEUED` | В очереди RQ | нет |
| `PROCESSING` | Worker обрабатывает кадры | нет |
| `COMPLETED` | Все кадры обработаны (`failed_frames = 0`; REJECTED допустимы) | да |
| `PARTIALLY_COMPLETED` | Часть кадров FAILED, часть обработана; `error_code = partial_frame_failures` | да |
| `FAILED` | Все кадры FAILED (`all_frames_failed`) либо фатальная ошибка pipeline | да |
| `CANCELLED` | Отменён оператором | да |

Стадии (`current_stage`, `ProcessingStage`): `VALIDATION → STORAGE →
FRAME_EXTRACTION → QUALITY_GATE → PRIVACY_FILTER → INFERENCE → NORMALIZATION →
TRACKING → GEOLOCATION → DEDUPLICATION → RISK_SCORING → PERSISTENCE → COMPLETED`.

Поля прогресса: `progress` (0…1), `total_frames`, `processed_frames`,
`failed_frames`, `rejected_frames`, `started_at`, `finished_at`,
`error_code`, `error_message`.

### Polling

Опрашивайте `GET /api/v1/jobs/{id}` каждые **1–2 секунды**, пока статус не
терминальный. WebSocket/SSE в MVP нет. Пример завершённого job:
[job-completed.json](../../contracts/examples/api/job-completed.json).

### Покадровые результаты

```
GET /api/v1/jobs/{id}/frames?status=FAILED&page=1&page_size=20
```

Envelope пагинации, порядок `frame_index` asc
([job-frames-page.json](../../contracts/examples/api/job-frames-page.json)).
Статусы кадра (`FrameStatus`): `PROCESSED`, `REJECTED` (с `reject_reason`),
`FAILED` (с `error_code`), `SKIPPED` (повторная обработка уже готового кадра).

Причины REJECTED (quality gate, прозрачные OpenCV-эвристики):
`low_resolution` (< 320×240), `blur` (Laplacian variance < 60),
`overexposure` (mean > 245), `underexposure` (mean < 10), `undecodable_frame`.
Пороги настраиваются (`QUALITY_*`), gate отключается `QUALITY_GATE_ENABLED=false`.

### Кадры видео и лимиты размерности

- Интервал извлечения кадров: `PROCESSING_FRAME_INTERVAL_SECONDS` (1 с),
  максимум `PROCESSING_MAX_FRAMES` = **2000** кадров на job.
- Защита от memory bomb: probe размерности **до decode**; отказ при
  > `PROCESSING_MAX_IMAGE_PIXELS` (64 Мп) или стороне >
  `PROCESSING_HARD_MAX_FRAME_SIDE` (8192 px).
- Кадры уменьшаются (downscale) до `PROCESSING_MAX_FRAME_SIDE` (4096 px)
  перед инференсом;
  **оригинал в хранилище не изменяется**, bbox детекций — в пикселях
  сохранённого (обработанного) кадра.

### Privacy (анонимизация)

В MVP действует `NoopPrivacyFilter`: анонимизация **не выполняется**, и это
честно отражается статусом `anonymization_status = NOT_APPLIED` у кадров/кропов.
Помечать `APPLIED` без реальной обработки запрещено архитектурно. Лица/номера
на кадрах не скрываются — доступ к медиа ограничен ролями
(OPERATOR/SERVICE/ADMIN), см. [privacy.md](../security/privacy.md).

## 4. Retry, cancel, зависшие job

### Retry

```
POST /api/v1/jobs/{id}/retry
```

- Допустимые статусы: `FAILED`, `PARTIALLY_COMPLETED`, `CANCELLED`, а также
  **зависший `PROCESSING`** (stale, см. ниже). Иначе → 409 `invalid_job_state`.
- Повторная обработка **идемпотентна**: обработанные кадры пропускаются
  (SKIPPED), дубли детекций исключаются unique-якорем
  `(processing_job_id, detection_id)`; ML-ответ сохраняется write-ahead,
  `request_id` детерминирован.
- Счётчики кадров пересчитываются по фактическим статусам.

### Cancel

```
POST /api/v1/jobs/{id}/cancel
```

- Допустимые статусы: `PENDING`, `QUEUED`, `PROCESSING`. Иначе → 409.
- Отмена **кооперативная**: pipeline проверяет статус CANCELLED каждые 10
  кадров; уже обработанные кадры и созданные сущности сохраняются.
- После cancel доступен retry (CANCELLED → QUEUED).

### Stale recovery (зависшие job)

- Stale-sweeper (при старте worker и периодически): `PROCESSING`/`QUEUED`
  без живого RQ-исполнения и без прогресса дольше
  `RQ_JOB_TIMEOUT + STALE_JOB_GRACE_SECONDS` (1800 + 120 = **1920 с**) →
  `FAILED` с `error_code = stale_processing` / `stale_queued`.
- Fencing исполнения (advisory lock) исключает двойную обработку живого job;
  статус `PROCESSED` никогда не понижается в `FAILED`.
- Retry stale `PROCESSING` разрешён напрямую (безопасно благодаря fencing).

## 5. Частичное завершение и ошибки pipeline

- Покадровые ошибки **не валят job**: кадр → FAILED, job →
  `PARTIALLY_COMPLETED` (`partial_frame_failures`, `"N frame(s) failed"`).
- Все кадры FAILED → job `FAILED` (`all_frames_failed`).
- Ошибки ML классифицированы: `ml_timeout`/`ml_unavailable` — retryable
  (повторы HTTP-провайдера: 1 + `ML_HTTP_RETRIES` попыток, экспоненциальный
  backoff; 4xx не повторяются), `ml_contract_violation`/`ml_inference_failed`
  — не retryable. См. [ml-contract.md](../integrations/ml-contract.md).
- UI-рекомендация: при `PARTIALLY_COMPLETED` показать долю неудачных кадров
  (`/frames?status=FAILED`) и предложить retry.

## 6. Результаты обработки

- `GET /observations?job_id=<id>` — наблюдения job (ML-предсказание в
  `object_type/condition_class/severity/detector_confidence`, человеческое —
  в `effective_*` и `review_status`; `dedup_explanation` — машиночитаемое
  объяснение дедупликации).
- `GET /assets`, `/defects` — реестр; `GET /map/*` — GeoJSON-слои.
- Дедупликация: `MATCHED`/`NEW_ASSET` создают/обновляют актив автоматически;
  `POSSIBLE_MATCH`/`AMBIGUOUS` **никогда не сливаются автоматически** —
  требуют решения оператора через review.

См. также: [workflows.md](workflows.md) (сквозной curl-сценарий),
[storage.md](../integrations/storage.md) (ключи, presign, lifecycle),
[errors.md](errors.md).
