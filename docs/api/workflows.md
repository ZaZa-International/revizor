# Сквозные сценарии (workflows)

Практические сценарии интеграции с реальными curl-примерами. Все ответы
соответствуют эталонным примерам
[`contracts/examples/api/`](../../contracts/examples/api/) (единый демо-сценарий:
объезд по Тверскому району Москвы, колодец с отсутствующей крышкой и шкаф с
открытой дверцей). Переменные окружения для удобства:

```bash
BASE=http://localhost:8000/api/v1
```

## Сценарий A: загрузка → обработка → подтверждение → карта → экспорт (9 шагов)

### Шаг 1. Login

```bash
curl -s -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username": "operator1", "password": "***"}'
```

Ответ 200 → [login-response.json](../../contracts/examples/api/login-response.json).
Сохраните токен:

```bash
TOKEN="<access_token из ответа>"
AUTH="Authorization: Bearer $TOKEN"
```

Ошибки: 401 `authentication_failed` (неверная пара), 422 (пустые поля),
429 `rate_limited` (10/мин с IP, 20/мин на username; ждите `Retry-After`).

### Шаг 2. Загрузка фото с GPS

```bash
curl -s -X POST "$BASE/uploads" \
  -H "$AUTH" \
  -H "Idempotency-Key: 11111111-2222-4333-8444-555555555555" \
  -F "file=@well_tverskaya_0005.jpg;type=image/jpeg" \
  -F "route_id=d290f1ee-6c54-4b01-90e6-d701748f0851" \
  -F 'metadata={"capture_started_at":"2026-11-15T12:00:00Z","gps_track":[{"timestamp":"2026-11-15T12:00:00Z","longitude":37.6165,"latitude":55.7554,"accuracy_m":4.5,"heading_deg":48.0,"speed_mps":5.2},{"timestamp":"2026-11-15T12:00:05Z","longitude":37.6173,"latitude":55.7558,"accuracy_m":4.0,"heading_deg":45.0,"speed_mps":5.5},{"timestamp":"2026-11-15T12:00:10Z","longitude":37.6181,"latitude":55.7562,"accuracy_m":4.2,"heading_deg":43.0,"speed_mps":5.4}]}'
```

Ответ 201 → [upload-created.json](../../contracts/examples/api/upload-created.json)
(`created: true`). Запомните `upload.id`
(`9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d` в примере).

Ошибки: 413 `payload_too_large` (> 2 GiB), 422 (формат/magic bytes/пустой
файл/битый metadata JSON), 403 (роль VIEWER), 429 (30 загрузок/мин).
Повтор того же файла → 200 `created: false`; чужой файл → redacted-карточка
([upload-duplicate-redacted.json](../../contracts/examples/api/upload-duplicate-redacted.json)).

### Шаг 3. Создание job

```bash
curl -s -X POST "$BASE/jobs" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: 66666666-7777-4888-9999-aaaaaaaaaaaa" \
  -d '{"upload_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
       "route_id": "d290f1ee-6c54-4b01-90e6-d701748f0851"}'
```

Ответ 201 — JobResponse (статус `PENDING`/`QUEUED`). Запомните `id` job
(`16fd2706-8baf-433b-82eb-8c7fada847da` в примере).

Ошибки: 409 `conflict` ("Upload already has an active processing job"),
409 `idempotency_conflict` (ключ уже использован с другим payload),
404 (чужой/несуществующий upload), 422.

### Шаг 4. Polling до терминального статуса

```bash
curl -s "$BASE/jobs/16fd2706-8baf-433b-82eb-8c7fada847da" -H "$AUTH"
```

Опрашивайте каждые 1–2 с, пока `status` не станет `COMPLETED`,
`PARTIALLY_COMPLETED`, `FAILED` или `CANCELLED`. Финальный ответ →
[job-completed.json](../../contracts/examples/api/job-completed.json)
(`progress: 1.0`, `processed_frames: 11`, `rejected_frames: 1`).

При `PARTIALLY_COMPLETED`/`FAILED` смотрите кадры:

```bash
curl -s "$BASE/jobs/16fd2706-8baf-433b-82eb-8c7fada847da/frames?status=FAILED" -H "$AUTH"
```

→ [job-frames-page.json](../../contracts/examples/api/job-frames-page.json)
(REJECTED с `reject_reason`, FAILED с `error_code`). Retry:

```bash
curl -s -X POST "$BASE/jobs/16fd2706-8baf-433b-82eb-8c7fada847da/retry" -H "$AUTH"
```

Ошибки: 409 `invalid_job_state` (retry/cancel в недопустимом статусе),
503 `storage_unavailable` / `ml_unavailable`, 504 `ml_timeout` (retryable,
backoff), 502 `ml_contract_violation` (не повторять — эскалация).

### Шаг 5. Наблюдения job

```bash
curl -s "$BASE/observations?job_id=16fd2706-8baf-433b-82eb-8c7fada847da&review_status=UNREVIEWED" \
  -H "$AUTH"
```

Карточка наблюдения:

```bash
curl -s "$BASE/observations/6ba7b810-9dad-41d4-80b5-e00d71c1a234" -H "$AUTH"
```

→ [observation-detail.json](../../contracts/examples/api/observation-detail.json):
bbox в пикселях кадра, `image_url`/`crop_url` (presigned, TTL 1 ч),
исходное ML-предсказание (`object_type`, `condition_class`, `severity`,
`detector_confidence`) vs человеческие `effective_*`, `dedup_result` и
машиночитаемый `dedup_explanation`. Для VIEWER URL медиа = `null`.

Ошибки: 404, 422 (невалидный uuid/фильтры).

### Шаг 6. Карточка актива

```bash
curl -s "$BASE/assets/f47ac10b-58cc-4372-a567-0e02b2c3d479" -H "$AUTH"
```

→ [asset-detail.json](../../contracts/examples/api/asset-detail.json):
`current_priority: 96.0` (HIGH_PRIORITY), `priority_factors` (прозрачная
разбивка risk-формулы), `version` для оптимистичной блокировки, координаты
`longitude/latitude`. Список с фильтрами:

```bash
curl -s "$BASE/assets?priority_band=HIGH_PRIORITY&sort_by=current_priority&order=desc" -H "$AUTH"
```

→ [assets-page.json](../../contracts/examples/api/assets-page.json).
История изменений: `GET /assets/{id}/history`; дефекты актива:
`GET /assets/{id}/defects`.

Ручное исправление (OPERATOR+):

```bash
curl -s -X PATCH "$BASE/assets/f47ac10b-58cc-4372-a567-0e02b2c3d479" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"display_name": "Колодец связи №4217 (Тверская ул.)", "expected_version": 2}'
```

Ошибки: 409 `conflict` ("Asset version mismatch; reload and retry") —
перечитайте карточку и повторите с новым `expected_version`; 422 (пустой
patch, override без reason).

### Шаг 7. Подтверждение дефекта (review)

```bash
curl -s -X POST "$BASE/reviews" \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: bbbbbbbb-cccc-4ddd-8eee-ffffffffffff" \
  -d '{"observation_id": "6ba7b810-9dad-41d4-80b5-e00d71c1a234",
       "decision": "CONFIRMED",
       "comment": "Крышка отсутствует — подтверждено по кропу. Передано в аварийную службу МГТС."}'
```

Ответ 201 → [review-created.json](../../contracts/examples/api/review-created.json).
Сервер атомарно применяет решение: observation → `review_status=CONFIRMED`,
связанный дефект → `CONFIRMED`, актив пересчитывается (risk, history,
`version` увеличивается). UI обновляет данные повторным чтением.

Исправление предсказания — `decision: CORRECTED` + хотя бы одно из
`corrected_asset_type / corrected_condition / corrected_defect_type /
corrected_severity` (иначе 422; исправления вне CORRECTED тоже 422).
История append-only: повторный review создаёт новую запись.

Ошибки: 422 (нет observation_id/defect_id, неизвестное состояние,
`reviewed_at` из будущего), 409 `idempotency_conflict`, 403 (VIEWER).

### Шаг 8. Карта

```bash
curl -s "$BASE/map/assets?bbox=37.55,55.70,37.70,55.80&priority_band=HIGH_PRIORITY" \
  -H "$AUTH"
```

→ [map-assets-featurecollection.json](../../contracts/examples/api/map-assets-featurecollection.json)
(GeoJSON `FeatureCollection`, координаты `[lon, lat]`). Объекты без GPS
(`UNAVAILABLE`) в слой не попадают — второй актив примера (шкаф) виден только
в списке. Слои дефектов/наблюдений/маршрутов: `/map/defects`,
`/map/observations`, `/map/routes`. Feed для MapLibre — напрямую.

Ошибки: 422 (битый bbox, неизвестный priority_band), 401.

### Шаг 9. Экспорт CSV/XLSX

```bash
# CSV дефектов (UTF-8 BOM, Excel-friendly)
curl -s -D headers.txt "$BASE/exports/defects?format=csv&status=CONFIRMED&severity_min=4" \
  -H "$AUTH" -o defects.csv

# XLSX активов с фильтрами списка
curl -s "$BASE/exports/assets?format=xlsx&priority_band=HIGH_PRIORITY" \
  -H "$AUTH" -o assets.xlsx

grep -i x-export-truncated headers.txt   # "X-Export-Truncated: true" при усечении
```

Ответ — файл (`Content-Disposition: attachment; filename="defects-export-….csv"`).
Фильтры идентичны списочным endpoint'ам. Лимит 50 000 строк; при усечении —
заголовок `X-Export-Truncated: true` (обязательно покажите пользователю).

Ошибки: 422 (невалидный format/фильтры), 503 `storage_unavailable` не
возникает (экспорты генерируются в памяти), 401/403.

## Сценарий B: очередь проверки оператором (review queue)

1. **Очередь**: `GET /observations?review_status=UNREVIEWED&sort_by=observed_at&order=asc`
   (+ `dedup_result=POSSIBLE_MATCH` или `AMBIGUOUS` — неразрешённые совпадения
   дедупликации; они никогда не сливаются автоматически).
2. **Карточка**: `GET /observations/{id}` — кроп (`crop_url`), исходное
   предсказание vs `effective_*`, `dedup_explanation` (оценки кандидатов,
   веса, пороги). Для POSSIBLE_MATCH сравните с активом-кандидатом
   (`dedup_explanation.candidates[].asset_id`).
3. **Решение**: `POST /reviews` — CONFIRMED / REJECTED / CORRECTED /
   NEEDS_MORE_INFORMATION (+ комментарий). NEEDS_MORE_INFORMATION переводит
   актив в полосу NEEDS_REVIEW.
4. **Обновление UI**: повторное чтение observation/asset/defect — сервер уже
   применил изменения; история — `/assets/{id}/history`
   (`change_source=HUMAN_REVIEW`).
5. **Контроль**: `GET /reviews?reviewer_id=…&date_from=…` — журнал проверок
   (append-only), `GET /analytics/overview` — доля проверенных наблюдений
   (`observations_reviewed_ratio`).

## Сценарий C: экспорт для отчётности

1. Подберите фильтры в UI списка (они один в один передаются в экспорт):
   `status`, `severity_min/max`, `bbox`, `date_from/to`, `asset_type`, …
2. `GET /exports/defects?format=xlsx&status=OPEN&severity_min=4` → скачайте
   blob (`responseType: "blob"` в axios/fetch; TS-типы бинарных ответов —
   string, используйте обычный fetch).
3. Проверьте `X-Export-Truncated`: при `true` сузьте выборку (bbox/даты) и
   повторите — порядок строк детерминирован, усечение воспроизводимо.
4. Колонки defects включают asset_type, priority, confidence, geolocation,
   review_status, observation_count — пригодно для сводок без дополнительных
   запросов.

## Общие рекомендации по ошибкам

- Всегда читайте `error.code` (не `message`) и сохраняйте `error.request_id`.
- 401 → relogin; 403 → ограничение роли; 429 → `Retry-After`;
  409 conflict версий → reload-retry; 502/503/504 → backoff-retry (кроме
  `ml_contract_violation`/`ml_inference_failed`).
- Мутации выполняйте с `Idempotency-Key` (uuid на операцию): безопасные
  повторы при сетевых сбоях без дублей.

См. также: [errors.md](errors.md), [upload-and-processing.md](upload-and-processing.md),
[authentication.md](authentication.md), [frontend-contract.md](../integrations/frontend-contract.md).
