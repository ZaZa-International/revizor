# Геопространственные данные

## Порядок координат и система отсчёта

- **Везде и всегда: `(longitude, latitude)`** — широта вторая. Это касается
  query-параметров (`bbox`, `longitude`/`latitude`), тел запросов (GPS-трек,
  `location`, `track` маршрута), полей ответов (`longitude`, `latitude`) и
  GeoJSON-геометрий (`coordinates: [lon, lat]`, RFC 7946).
- Система координат — **WGS84, SRID 4326**. Хранение — PostGIS `Geography`
  (POINT для объектов/наблюдений, LINESTRING для треков маршрутов).
- Диапазоны: `longitude ∈ [-180, 180]`, `latitude ∈ [-90, 90]`. Выход за
  диапазон, NaN/Inf → 422. Пара координат передаётся только совместно.
- Расстояния — **метры**, только через geography (`ST_Distance`,
  `ST_DWithin`, `ST_Length`); не путайте geometry и geography.
- Перестановка lon/lat, дающая обе координаты в допустимых диапазонах
  (например, Москва ↔ «зеркальная» точка), сервером не детектируется —
  ответственность на стороне клиента (известное ограничение, GEO-4 аудита).

## GeoJSON map-слои

Четыре слоя для MapLibre / любого GIS-frontend. Ответ — `FeatureCollection`
(RFC 7946); геометрия `Point` (assets/defects/observations) или `LineString`
(routes). Координаты строго `[longitude, latitude]`.

```
GET /api/v1/map/assets?bbox=37.55,55.70,37.70,55.80&priority_band=HIGH_PRIORITY&limit=1000
GET /api/v1/map/defects?bbox=…&status=OPEN&severity_min=4
GET /api/v1/map/observations?bbox=…&job_id=…&date_from=…&date_to=…
GET /api/v1/map/routes?limit=100
```

Пример ответа:
[map-assets-featurecollection.json](../../contracts/examples/api/map-assets-featurecollection.json).

**Объекты без GPS (`geolocation_status = UNAVAILABLE`) в map-слои не
попадают** — показывайте их в списочном представлении (`/assets` и т.д.).

### Properties слоя assets (`AssetMapProperties`)

| Поле | Тип | Описание |
|---|---|---|
| `id` | string (uuid) | Идентификатор актива |
| `asset_type` | string | Тип объекта (реестр домена) |
| `display_name` | string \| null | Операторское имя |
| `current_condition` | string \| null | Текущее состояние |
| `current_severity` | int \| null | Severity 1…5 |
| `current_priority` | float \| null | Приоритет 0…100 |
| `priority_band` | enum \| null | HIGH_PRIORITY / MEDIUM_PRIORITY / LOW_PRIORITY / NEEDS_REVIEW |
| `geolocation_status` | enum | CONFIRMED / ESTIMATED (UNAVAILABLE исключён из слоя) |
| `location_accuracy_m` | float \| null | Точность координаты, метры |
| `lifecycle_status` | enum | ACTIVE / INACTIVE / RETIRED / UNKNOWN |
| `last_observed_at` | datetime \| null | Последнее наблюдение |

### Properties слоя defects (`DefectMapProperties`)

| Поле | Тип |
|---|---|
| `id` | string (uuid дефекта) |
| `asset_id` | string (uuid актива) |
| `asset_type` | string |
| `defect_type` | string |
| `severity` | int (1…5) |
| `status` | enum (OPEN / CONFIRMED / IN_PROGRESS / RESOLVED / REJECTED) |
| `current_priority` | float \| null (приоритет актива) |
| `first_detected_at` | datetime |
| `last_detected_at` | datetime |

Геометрия дефекта — координата его актива.

### Properties слоя observations (`ObservationMapProperties`)

| Поле | Тип |
|---|---|
| `id` | string (uuid наблюдения) |
| `asset_id` | string \| null (null для неразрешённых дедупликацией) |
| `object_type` | string |
| `condition_class` | string \| null |
| `detector_confidence` | float (0…1) |
| `review_status` | enum (UNREVIEWED / CONFIRMED / REJECTED / CORRECTED / NEEDS_MORE_INFORMATION) |
| `dedup_result` | enum \| null (MATCHED / NEW_ASSET / POSSIBLE_MATCH / AMBIGUOUS) |
| `observed_at` | datetime |
| `processing_job_id` | string (uuid job) |

### Properties слоя routes (`RouteMapProperties`)

| Поле | Тип |
|---|---|
| `id` | string (uuid маршрута) |
| `name` | string |
| `vehicle_id` | string \| null |
| `started_at` / `finished_at` | datetime \| null |
| `total_distance_m` | float \| null (длина трека, метры, PostGIS) |

Геометрия — `LineString` из упорядоченных пар `[lon, lat]`.

## bbox-фильтр

Формат: **`bbox=min_lon,min_lat,max_lon,max_lat`** (4 числа через запятую,
пробелы вокруг чисел допустимы). Пример: `bbox=37.55,55.70,37.70,55.80`.

- Валидация: ровно 4 числовых значения; `min ≤ max` по каждой оси; диапазоны
  lon/lat. Нарушение → 422 `validation_error`.
- Применяется к `/assets`, `/observations`, map-слоям и экспортам
  (PostGIS `ST_Intersects` по GiST-индексу).
- Пустая строка трактуется как отсутствие фильтра.

## Nearby-поиск

```
GET /api/v1/assets/nearby?longitude=37.6173&latitude=55.7558&radius_m=100&asset_type=telecom_well&limit=10
```

| Параметр | По умолчанию | Ограничения |
|---|---|---|
| `longitude` / `latitude` | обязательны | диапазоны WGS84 |
| `radius_m` | 50 | > 0, ≤ 5000 |
| `asset_type` | — | опциональный фильтр типа |
| `limit` | 10 | 1…100 |

Ответ — `{items: [{id, asset_type, display_name, distance_m, current_priority}], total}`;
`distance_m` — расстояние по большому кругу (geography, метры), сортировка по
возрастанию расстояния. Объекты без координат не участвуют.

## Статусы геолокации и точность

Координаты наблюдения/актива определяются по GPS-треку загрузки
(`metadata.gps_track`) относительно времени кадра (`observed_at`):

| Статус | Условие | Семантика |
|---|---|---|
| `CONFIRMED` | Разрыв до ближайшей точки трека **≤ 2 с** и точность точки **≤ 50 м** (`GPS_MAX_ACCURACY_M`; отсутствие accuracy_m допускается) | Координата надёжна |
| `ESTIMATED` | Разрыв ≤ 2 с, но accuracy_m > 50 м; **или** интерполяция между точками при разрыве ≤ 10 с | Координата оценочная; `location_accuracy_m` отражает неопределённость |
| `UNAVAILABLE` | Трека нет, или разрыв > 10 с | Координат нет (`longitude/latitude = null`) |
| `INVALID` | Зарезервировано для некорректных данных | — |

Правила:

- **Координаты никогда не выдумываются.** Без GPS — `UNAVAILABLE` и причина
  (`no_gps_track`, `gps_gap_too_large:<N>s`); в БД действует CHECK
  location ↔ status.
- Naive ISO-timestamps трека нормализуются к UTC (assume-UTC policy, GEO-1):
  смешанные naive/aware треки не валят job.
- Невалидные точки трека (не-finite/out-of-range `accuracy_m`, `heading_deg`,
  `speed_mps`, битые координаты) пропускаются и считаются, а не используются.
- `geolocation_source`: GPS / MANUAL / MAP_MATCHING / VISUAL / UNKNOWN.
  Ручное исправление координаты оператором (`PATCH /assets` → `location`)
  даёт MANUAL.
- Для CONFIRMED-наблюдений `location_accuracy_m` ≤ 50; UI может показывать
  ESTIMATED-объекты с меньшей уверенностью (например, полупрозрачными).

## Треки маршрутов

`POST /api/v1/routes` принимает `track: [[lon, lat], …]` (2…10000 точек);
`total_distance_m` вычисляется PostGIS (`ST_Length` geography). Ответ
`GET /routes/{id}` содержит `track_geojson` (LineString); в списках
`track_geojson = null` (экономия трафика).

См. также: [upload-and-processing.md](upload-and-processing.md) (gps_track),
[pagination-filtering.md](pagination-filtering.md),
[docs/database/geospatial.md](../database/geospatial.md).
