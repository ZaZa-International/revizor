# Пагинация, сортировка и фильтры

## Envelope списка

Все списочные endpoint'ы (включая кадры job и историю актива) возвращают
единый конверт:

```json
{
  "items": [ "…" ],
  "total": 137,
  "page": 1,
  "page_size": 20,
  "pages": 7
}
```

| Поле | Смысл |
|---|---|
| `items` | Элементы текущей страницы |
| `total` | Всего элементов, удовлетворяющих фильтрам |
| `page` | Текущая страница (≥ 1) |
| `page_size` | Размер страницы (1…100) |
| `pages` | Всего страниц (`ceil(total / page_size)`) |

Примеры: [assets-page.json](../../contracts/examples/api/assets-page.json),
[job-frames-page.json](../../contracts/examples/api/job-frames-page.json),
[defects-page.json](../../contracts/examples/api/defects-page.json),
[routes-page.json](../../contracts/examples/api/routes-page.json).

## Общие параметры

| Параметр | Тип | По умолчанию | Ограничения |
|---|---|---|---|
| `page` | int | 1 | ≥ 1 |
| `page_size` | int | 20 | 1…100 (превышение → 422; серверный clamp — backstop) |
| `sort_by` | string | `created_at`* | Whitelist ресурса (ниже); неизвестное значение → **422** |
| `order` | `asc` \| `desc` | `desc` | |
| `date_from` / `date_to` | ISO 8601 datetime | — | Включительный диапазон по дате ресурса; `date_from > date_to` → **422** |
| `search` | string | — | Подстрока без учёта регистра, ≤ 128 символов (где поддерживается) |
| `bbox` | string | — | `min_lon,min_lat,max_lon,max_lat` (см. [geospatial.md](geospatial.md)) |

\* Сортировка по умолчанию — `created_at` descending; исключения указаны ниже.
Naive-даты (без таймзоны) трактуются как UTC.

## Sort whitelists по ресурсам

Значения `sort_by` зафиксированы как enum в OpenAPI (Literal-типы). Неизвестное
значение → 422 `validation_error` (тихий fallback запрещён).

| Ресурс | Допустимые `sort_by` | По умолчанию |
|---|---|---|
| `/assets` | `created_at`, `last_observed_at`, `current_priority`, `current_severity`, `asset_type` | `created_at` |
| `/jobs` | `created_at`, `status`, `started_at`, `finished_at` | `created_at` |
| `/observations` | `observed_at`, `created_at`, `detector_confidence` | `created_at` |
| `/defects` | `created_at`, `last_detected_at`, `severity`, `status` | `created_at` |
| `/reviews` | `reviewed_at`, `created_at` | `created_at` |
| `/routes` | `created_at`, `started_at`, `name`, `total_distance_m` | `created_at` |
| `/uploads` | `created_at`, `file_size`, `original_filename` | `created_at` |
| `/jobs/{id}/frames` | — (всегда `frame_index` asc) | `frame_index` |
| `/assets/{id}/history` | — (всегда новые сверху) | `detected_at` desc |
| `/assets/{id}/observations` | — (`observed_at`, `order` asc/desc) | `observed_at` desc |
| `/assets/{id}/defects` | — (`last_detected_at` desc) | `last_detected_at` desc |

## Поле даты по ресурсам (`date_from` / `date_to`)

Фильтр дат применяется к **разному полю** в зависимости от ресурса —
учитывайте это в UI-подписях:

| Ресурс | Поле фильтрации |
|---|---|
| `/uploads` | `created_at` (время загрузки) |
| `/jobs` | `created_at` (время создания задачи) |
| `/assets` | `last_observed_at` (последнее наблюдение) |
| `/observations` | `observed_at` (время съёмки кадра) |
| `/defects` | `last_detected_at` (последнее обнаружение) |
| `/reviews` | `reviewed_at` (время проверки) |
| `/routes` | `started_at` (начало объезда) |
| `/map/observations` | `observed_at` |

Инвертированный диапазон (`date_from > date_to`) → 422 `validation_error`
("date_from must be earlier than or equal to date_to").

## Поиск (`search`)

- Поддерживается: `/assets` (по `display_name` и `external_id`), `/routes`
  (по `name`), `/uploads` (по `original_filename`).
- Регистронезависимая подстрока (`ILIKE %…%`); длина ≤ 128 символов
  (assets/routes; превышение → 422).
- LIKE-метасимволы `%`, `_`, `\` **экранируются сервером** — поиск literal'ный,
  инъекция wildcards невозможна.

## Фильтры по ресурсам

| Ресурс | Фильтры |
|---|---|
| `/uploads` | `media_type` (IMAGE\|VIDEO), `route_id`, `search`, `date_from/to` |
| `/jobs` | `status` (JobStatus), `upload_id`, `route_id`, `date_from/to` |
| `/jobs/{id}/frames` | `status` (PROCESSED\|REJECTED\|FAILED\|SKIPPED) |
| `/assets` | `asset_type`, `geolocation_status`, `lifecycle_status`, `priority_band`, `bbox`, `search`, `date_from/to` |
| `/observations` | `asset_id`, `job_id`, `object_type`, `review_status`, `dedup_result`, `bbox`, `date_from/to` |
| `/defects` | `asset_id`, `status`, `defect_type`, `severity_min`, `severity_max` (1…5), `date_from/to` |
| `/reviews` | `observation_id`, `defect_id`, `reviewer_id`, `decision`, `date_from/to` |
| `/routes` | `vehicle_id`, `search`, `date_from/to` |
| `/map/assets` | `bbox`, `asset_type`, `priority_band`, `limit` |
| `/map/defects` | `bbox`, `status`, `severity_min`, `limit` |
| `/map/observations` | `bbox`, `job_id`, `date_from/to`, `limit` |
| `/map/routes` | `limit` |
| `/exports/*` | Те же фильтры, что у соответствующих списков (parity), + `format` |

Замечание по именованию: query-параметр `job_id` в `/observations` и
`/map/observations` соответствует полю ответа `processing_job_id`.

## Лимиты map-слоёв и nearby

Map-слои не пагинируются — используется `limit` (усечение детерминированное
не гарантируется; для полных выборок сужайте `bbox`):

| Endpoint | `limit` по умолчанию | Максимум |
|---|---|---|
| `/map/assets`, `/map/defects`, `/map/observations` | 1000 | **5000** |
| `/map/routes` | 100 | 1000 |
| `/assets/nearby` | 10 | 100 (радиус `radius_m` ≤ 5000) |

## Пагинация кадров и истории

Начиная с 0.2.0 (breaking pre-1.0, см. CHANGELOG):

- `GET /jobs/{id}/frames` — envelope `{items, total, page, page_size, pages}`,
  порядок `frame_index` asc, фильтр `status`. кадров в job ≤ 2000.
- `GET /assets/{id}/history` — envelope, новые записи сверху
  (`change_source`: ML_PREDICTION / HUMAN_REVIEW / MANUAL_EDIT / SYSTEM,
  `is_physical_change`).

## Экспорты

`/exports/assets|observations|defects` принимают те же фильтры, что и списки,
плюс `format=csv|xlsx`. Пагинации нет: выгружается вся выборка, жёсткий лимит
**50 000 строк**; при усечении ответ содержит заголовок
`X-Export-Truncated: true` (UI обязан показать факт усечения). CSV — UTF-8 с
BOM (Excel-friendly). Подробности — [workflows.md](workflows.md).

См. также: [geospatial.md](geospatial.md), [errors.md](errors.md),
[frontend-contract.md](../integrations/frontend-contract.md).
