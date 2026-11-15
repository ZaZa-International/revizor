# Frontend Integration Contract — MGTS Infrastructure Intelligence

Контракт для параллельной работы frontend-команды. Источник истины по схемам —
OpenAPI: `contracts/openapi/openapi.json` (генерируется `make openapi`), Swagger UI на `/docs`.
Версия API: **v1**. Все примеры ниже проверены контрактными тестами
(`backend/tests/contracts/test_frontend_contract.py`).

## 1. Base URL и аутентификация

- Base URL (dev): `http://localhost:8000`
- Префикс API: `/api/v1`
- Auth: JWT Bearer. `POST /api/v1/auth/login` с JSON `{"username", "password"}` →
  `{"access_token", "token_type": "bearer", "expires_in_minutes", "user": {...}}`.
  Далее заголовок `Authorization: Bearer <access_token>`.
- Роли: `ADMIN`, `OPERATOR`, `VIEWER`, `SERVICE`. VIEWER — только чтение;
  OPERATOR/SERVICE/ADMIN — загрузки, jobs, reviews, PATCH. Ошибка доступа — 403.
- Токен протухает (по умолчанию 60 мин) → 401 `authentication_failed` → повторный login.
- Каждый ответ несёт `x-request-id` (пробрасывайте при обращениях в поддержку).
- CORS: разрешённые origin задаются `CORS_ORIGINS` (по умолчанию localhost:3000/5173).

## 2. Пагинация, сортировка, фильтры

Списочные endpoints принимают:

| Параметр | Тип | По умолчанию | Ограничения |
|---|---|---|---|
| `page` | int | 1 | ≥1 |
| `page_size` | int | 20 | 1…100 |
| `sort_by` | string | created_at* | whitelist полей endpoint'а |
| `order` | `asc`\|`desc` | desc | |
| `date_from` / `date_to` | ISO 8601 | — | диапазон по дате сущности |
| `bbox` | string | — | `min_lon,min_lat,max_lon,max_lat` |
| `search` | string | — | там, где поддерживается |

\* Сортировка по умолчанию — по дате создания/наблюдения; конкретный whitelist смотрите в OpenAPI.

Envelope ответа списка:

```json
{
  "items": [ ... ],
  "total": 137,
  "page": 1,
  "page_size": 20,
  "pages": 7
}
```

## 3. Единый формат ошибок

Любая ошибка (4xx/5xx):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [{"field": "body.longitude", "message": "Input should be less than or equal to 180", "type": "less_than_equal"}],
    "request_id": "6f1c..."
  }
}
```

Коды: `not_found` (404), `validation_error` (422), `authentication_failed` (401),
`permission_denied` (403), `conflict` (409), `invalid_job_state` (409),
`idempotency_conflict` (409), `rate_limited` (429, заголовок `Retry-After`),
`storage_unavailable` (503), `ml_unavailable` (503), `ml_timeout` (504),
`ml_contract_violation` (502), `internal_error` (500).

## 4. Idempotency

Для `POST /uploads`, `POST /jobs`, `POST /reviews` поддерживается заголовок
`Idempotency-Key: <uuid>`. Повтор с тем же ключом возвращает сохранённый ответ
(статус и тело идентичны), не создавая дубль. Рекомендуется для всех мутаций.

## 5. Основные endpoints

### Health / ML
- `GET /health`, `/health/live`, `/health/ready` — без auth.
- `GET /metrics` — Prometheus.
- `GET /api/v1/ml/health` → `{status, model_loaded, provider, details}`.
- `GET /api/v1/ml/model-info` → `{name, version, schema_version}`.

### Uploads
- `POST /api/v1/uploads` — multipart: `file` (обязательно), `route_id` (uuid, опц.),
  `metadata` (JSON-строка, опц.; см. workflow ниже). Ответ 201 (новый) / 200 (дубликат
  по checksum): `{"upload": {...}, "created": true}`.
  Поля upload: `id, original_filename, storage_key, content_type, file_size,
  checksum_sha256, media_type (IMAGE|VIDEO), uploaded_by, route_id, metadata,
  created_at, presigned_url`.
- `GET /api/v1/uploads` — фильтры `media_type, route_id, search, date_from, date_to`.
- `GET /api/v1/uploads/{id}` · `DELETE /api/v1/uploads/{id}` (409, если есть jobs).
- Допустимые форматы: jpeg/png/webp, mp4/avi/mov/webm; проверяются расширение,
  declared MIME и magic bytes. Лимит размера — `MAX_UPLOAD_SIZE_BYTES` (2 GiB default).

### Processing jobs
- `POST /api/v1/jobs` — `{"upload_id", "route_id"?, "options"?}` → 201/200, JobResponse.
- `GET /api/v1/jobs/{id}` — статус/прогресс:
  `status: PENDING|QUEUED|PROCESSING|COMPLETED|PARTIALLY_COMPLETED|FAILED|CANCELLED`,
  `progress 0…1`, `current_stage`, `total_frames/processed_frames/failed_frames/rejected_frames`,
  `error_code/error_message`. Polling каждые 1–2 с, пока статус не терминальный.
- `GET /api/v1/jobs` — фильтры `status, upload_id, route_id, date_*`.
- `GET /api/v1/jobs/{id}/frames` — покадровые результаты (REJECTED с reason, FAILED с code).
- `POST /api/v1/jobs/{id}/retry` (FAILED/PARTIALLY_COMPLETED/CANCELLED) ·
  `POST /api/v1/jobs/{id}/cancel`. Invalid state → 409 `invalid_job_state`.

### Assets
- `GET /api/v1/assets` — фильтры `asset_type, geolocation_status, lifecycle_status,
  priority_band, bbox, search, date_*`; сортировка `current_priority, current_severity,
  last_observed_at, asset_type, created_at`.
- `GET /api/v1/assets/{id}` — AssetResponse (включая `longitude/latitude`,
  `current_condition, current_severity, current_priority 0…100, priority_band
  (HIGH_PRIORITY|MEDIUM_PRIORITY|LOW_PRIORITY|NEEDS_REVIEW), priority_factors,
  priority_policy_version, version`).
- `PATCH /api/v1/assets/{id}` — `display_name, external_id, lifecycle_status,
  priority_override (+обязательный priority_override_reason), location
  {longitude, latitude, accuracy_m?}, expected_version` (оптимистичная блокировка;
  конфликт версий → 409).
- `GET /api/v1/assets/{id}/history` — изменения состояния с `change_source`
  (ML_PREDICTION/HUMAN_REVIEW/MANUAL_EDIT) и `is_physical_change`.
- `GET /api/v1/assets/{id}/observations` · `GET /api/v1/assets/{id}/defects` — пагинация.
- `GET /api/v1/assets/nearby?longitude=&latitude=&radius_m=&asset_type=&limit=`.

### Observations
- `GET /api/v1/observations` — фильтры `asset_id, job_id, object_type, review_status
  (UNREVIEWED|CONFIRMED|REJECTED|CORRECTED|NEEDS_MORE_INFORMATION), dedup_result
  (MATCHED|NEW_ASSET|POSSIBLE_MATCH|AMBIGUOUS), bbox, date_*`.
- `GET /api/v1/observations/{id}` — включает `bbox` (пиксели), `image_url`, `crop_url`
  (presigned или `/api/v1/files/...`), `raw` ML-поля НЕ отдаются; исходное предсказание
  в `object_type/condition_class/severity/detector_confidence`, человеческое — в
  `effective_*` и `review_status`. `dedup_explanation` — машиночитаемое объяснение.

### Defects
- `GET /api/v1/defects` — фильтры `asset_id, status (OPEN|CONFIRMED|IN_PROGRESS|
  RESOLVED|REJECTED), defect_type, severity_min, severity_max, date_*`.
- `GET /api/v1/defects/{id}` (+`observation_count`) ·
  `PATCH /api/v1/defects/{id}` — `status, severity 1…5, description`.

### Reviews (human-in-the-loop)
- `POST /api/v1/reviews` —
  `{"observation_id"?, "defect_id"?, "decision": "CONFIRMED|REJECTED|CORRECTED|NEEDS_MORE_INFORMATION",
  "corrected_asset_type"?, "corrected_condition"?, "corrected_defect_type"?,
  "corrected_severity"?, "comment"?, "reviewed_at"?}`.
  CORRECTED требует ≥1 исправления; исправления вне CORRECTED → 422.
  История append-only: повторный review создаёт новую запись.
- `GET /api/v1/reviews` — фильтры `observation_id, defect_id, reviewer_id, decision, date_*`.
- `GET /api/v1/reviews/{id}`.

### Routes
- `POST /api/v1/routes` — `{"name", "vehicle_id"?, "started_at"?, "finished_at"?,
  "track": [[lon,lat], ...] (≥2 точек), "metadata"?}` → `total_distance_m` считается PostGIS.
- `GET /api/v1/routes` · `GET /api/v1/routes/{id}` (+`track_geojson` LineString).

### Map (GeoJSON для MapLibre)
- `GET /api/v1/map/assets?bbox=&asset_type=&priority_band=&limit=`
- `GET /api/v1/map/defects?bbox=&status=&severity_min=`
- `GET /api/v1/map/observations?bbox=&job_id=&date_from=&date_to=`
- `GET /api/v1/map/routes`

Ответ — `FeatureCollection`; координаты строго `[longitude, latitude]`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [37.6173, 55.7558]},
      "properties": {"id": "…", "asset_type": "telecom_well", "current_priority": 87.5, "priority_band": "HIGH_PRIORITY", "...": "..."}
    }
  ]
}
```

Объекты без GPS в map-слои не попадают (`geolocation_status=UNAVAILABLE`);
показывайте их в списочном представлении.

### Analytics
- `GET /api/v1/analytics/overview` — счётчики, распределения по типам/статусам/severity/bands.
- `GET /api/v1/analytics/defects` — агрегация по типам дефектов.
- `GET /api/v1/analytics/coverage` — сетка покрытия surveyed area:
  `grid_cell_m, total_cells, covered_cells, coverage_ratio, gap_cells,
  covered_cell_counts [{cx, cy, observations}], routes [...]`.
  `cx/cy` — индексы ячейки от `area_bbox.min_longitude/min_latitude`.

### Exports
- `GET /api/v1/exports/assets|defects|observations?format=csv|xlsx` + те же фильтры,
  что у списков. Ответ — файл (`Content-Disposition: attachment`).
  CSV — UTF-8 с BOM (Excel-friendly). Колонки defects включают asset_type, priority,
  confidence, geolocation, review_status, observation_count.

### Files
- `GET /api/v1/files/{storage_key}` — auth-protected скачивание (local storage).
  Для S3 используйте `presigned_url`/`image_url` напрямую (срок жизни ограничен).

## 6. Workflows

### Upload → Processing → результат
1. `POST /uploads` (multipart). GPS кладите в `metadata` JSON-строкой:
   ```json
   {"capture_started_at": "2026-11-15T12:00:00Z",
    "gps_track": [{"timestamp": "2026-11-15T12:00:00Z", "longitude": 37.6173, "latitude": 55.7558, "accuracy_m": 4.0, "heading_deg": 45, "speed_mps": 8}]}
   ```
   Без GPS объекты создаются со статусом UNAVAILABLE — это нормально.
2. `POST /jobs {"upload_id": ...}` (+`Idempotency-Key`).
3. Poll `GET /jobs/{id}` до терминального статуса; при PARTIALLY_COMPLETED смотрите
   `/jobs/{id}/frames` и предлагайте retry.
4. `GET /observations?job_id=...`, `GET /assets?...` — результат; карта `/map/*`.

### Review
1. Очередь: `GET /observations?review_status=UNREVIEWED` (+`dedup_result=POSSIBLE_MATCH`
   для неразрешённых совпадений).
2. Карточка: `image_url`/`crop_url`, исходное предсказание vs `effective_*`.
3. `POST /reviews` с решением и исправлениями; UI обновляет observation/asset/defect
   повторным чтением (сервер уже применил изменения).

### Export
`GET /exports/defects?format=xlsx&status=OPEN&severity_min=4` → скачать файл.
Фильтры UI передавайте один в один.

## 7. Генерация TypeScript-клиента

```bash
npx openapi-typescript contracts/openapi/openapi.json -o src/api/schema.d.ts
# или полноценный клиент:
npx orval --input contracts/openapi/openapi.json --output src/api/client.ts
```

OpenAPI обновляется командой `make openapi` и коммитится; ломающие изменения
сопровождаются записью в CHANGELOG и версией контракта.

## 8. Что НЕ входит в контракт MVP

WebSocket/SSE (используйте polling jobs), управление пользователями через API
(bootstrap admin + seed), загрузка GPS-треков отдельным endpoint (кладите в metadata
upload или создавайте Route), реальные ML-детекции (mock до подключения ML-команды).
