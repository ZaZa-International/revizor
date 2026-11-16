# Геопространственный слой (PostGIS)

СУБД: PostgreSQL 16 + PostGIS 3.4. Гео-ORM: GeoAlchemy2 (`>=0.21,<0.22`),
геометрия в Python: Shapely (`>=2.0,<3`). Расширение `postgis` создаётся миграцией
`backend/migrations/versions/0001_initial.py:57`.

## geography vs geometry: выбор в пользу geography

Все пространственные колонки объявлены как **`Geography`**, а не `Geometry`:

| Таблица | Колонка | Тип | Код |
|---------|---------|-----|-----|
| assets | location | `GEOGRAPHY(POINT, 4326)` | `models/asset.py:45` |
| observations | location | `GEOGRAPHY(POINT, 4326)` | `models/observation.py:95` |
| routes | track_geometry | `GEOGRAPHY(LINESTRING, 4326)` | `models/route.py:25` |

**Почему geography:** функции `ST_Distance` / `ST_DWithin` / `ST_Length` для
`geography` возвращают **метры** (сфероидальная модель WGS84), без ручного
пересчёта градусов в метры и без выбора проекции. Это критично для дедупликации
(радиусы 8–25 м) и поиска nearby (радиус в метрах). `geometry` дал бы расстояния
в градусах, что потребовало бы проекции или эвристик.

Исключение: в аналитике покрытия координаты извлекаются через приведение к
`Geometry` — `func.ST_X(Observation.location.cast(Geometry))` и `ST_Y`
(`services/analytics.py:131-132`), потому что `ST_X/ST_Y` определены для
geometry, а не geography. Это точечное приведение для извлечения lon/lat,
не меняющее выбор geography для метрических операций.

## SRID 4326 и строгий порядок (longitude, latitude)

- Все гео-данные — **WGS84, SRID 4326**.
- Порядок координат **всегда `(longitude, latitude)`** (долгота, широта).
  Это зафиксировано в `domain/geospatial/models.py` и `schemas/ml.py`.
- `GeoPoint` (`models.py:31`) хранит `longitude`, `latitude`; `to_wkt()` →
  `POINT(lon lat)`; `to_geojson()` → `{"type":"Point","coordinates":[lon,lat]}`.
- ML-контракт (`schemas/ml.py::MLFrameMetadata`) требует предоставления
  longitude и latitude **только парой** (`_coords_pair`), диапазоны
  lon `[-180,180]`, lat `[-90,90]`.

### WKTElement

Геометрии передаются в БД через `geoalchemy2.WKTElement` с `srid=4326`:

```python
# repositories/assets.py:20
def point_element(point: GeoPoint) -> WKTElement:
    return WKTElement(point.to_wkt(), srid=4326)

# repositories/assets.py:24
def bbox_element(bbox: BoundingBox) -> WKTElement:
    return WKTElement(bbox.to_wkt_polygon(), srid=4326)
```

LINESTRING маршрута строится в `api/v1/routes.py:27-28`:
```python
coords = ", ".join(f"{lon} {lat}" for lon, lat in body.track)
track_element = WKTElement(f"LINESTRING({coords})", srid=4326)
```

## Используемые функции PostGIS (с ссылками на код)

| Функция | Назначение | Где |
|---------|-----------|-----|
| `ST_DWithin(geog, geog, radius_m)` | фильтр «в радиусе N метров» (использует GiST) | `repositories/assets.py:112` (find_candidates), `services/geospatial.py:199` (nearest_assets) |
| `ST_Distance(geog, geog)` | расстояние в метрах, сортировка по близости | `repositories/assets.py:107,114`, `services/geospatial.py:196,201` |
| `ST_Intersects(geog, polygon)` | bbox-фильтр слоёв и списков | `services/geospatial.py:59,103,140`, `repositories/assets.py:60`, `repositories/observations.py:71`, `services/analytics.py:139` |
| `ST_Length(geog)` | длина трека маршрута в метрах | `api/v1/routes.py:43` |
| `ST_X / ST_Y` (cast Geometry) | извлечение lon/lat для grid-покрытия | `services/analytics.py:131-132` |

> **О `ST_AsGeoJSON`.** В коде эта функция **не используется**. GeoJSON строится
> на стороне Python: `geoalchemy2.shape.to_shape` → `shapely.geometry.mapping`
> (`services/geospatial.py:29-33`, `api/v1/serializers.py:21-25,64`).
> Это осознанный подход: сериализация в GeoJSON выполняется в application/API-слое,
> а не в SQL. Документ фиксирует фактическую реализацию.

### Пример: поиск кандидатов дедупликации

`AssetRepository.find_candidates` (`repositories/assets.py:96-118`) — полностью
в PostGIS, только `ACTIVE` активы того же типа, в радиусе, ближайшие сверху:

```python
element = point_element(point)
stmt = (
    select(Asset, func.ST_Distance(Asset.location, element).label("distance_m"))
    .where(
        Asset.location.is_not(None),
        Asset.asset_type == asset_type,
        Asset.lifecycle_status == LifecycleStatus.ACTIVE,
        func.ST_DWithin(Asset.location, element, radius_m),
    )
    .order_by(func.ST_Distance(Asset.location, element).asc())
    .limit(limit)  # DEDUP_MAX_CANDIDATES, default 50 (0.2.0; было 10)
)
```

## GiST-индексы

Пространственные индексы создаются миграцией (`postgresql_using="gist"`):

| Индекс | Таблица.колонка | Миграция |
|--------|-----------------|----------|
| `ix_assets_location` | assets.location | `0001_initial.py:234` |
| `ix_observations_location` | observations.location | `0001_initial.py:294` |
| `ix_routes_track_geometry` | routes.track_geometry | `0001_initial.py:94` |

В моделях GeoAlchemy2 `spatial_index=False` (индексы создаются вручную в миграции,
чтобы контролировать имя и тип). GiST ускоряет `ST_DWithin` / `ST_Intersects`
(index scan вместо seq scan).

## Формат bbox-фильтра

Строка **`min_lon,min_lat,max_lon,max_lat`** (4 числа через запятую).
Парсинг: `BoundingBox.parse` (`domain/geospatial/models.py:88-97`),
валидация диапазонов и `min <= max`. В API передаётся query-параметром `bbox`
(`dependencies.py::parse_bbox` → `ValidationAppError` при ошибке).

Пример: `bbox=37.55,55.70,37.70,55.80` (демо-область Москва,
`Settings.demo_area_bbox`). `to_wkt_polygon()` строит замкнутый POLYGON
(`models.py:99-104`), который передаётся в `ST_Intersects`.

Используется в: `/map/assets`, `/map/defects`, `/map/observations`,
списках `/assets`, `/observations`, экспортах, аналитике покрытия.

## Контракт GeoJSON на выходе

Слои `/map/*` возвращают **GeoJSON FeatureCollection**
(`services/geospatial.py::_collection/_feature/_geojson`):

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {"type": "Point", "coordinates": [37.6173, 55.7558]},
      "properties": {"id": "...", "asset_type": "telecom_well", "priority_band": "HIGH_PRIORITY", "...": "..."}
    }
  ]
}
```

- `geometry` — Shapely `mapping(to_shape(...))`; для отсутствующей локации — `null`.
- Координаты в порядке `[longitude, latitude]` (RFC 7946).
- Лимиты: `MAP_MAX_FEATURES = 5000` (`services/geospatial.py:26`);
  `/map/routes` до 1000. Слои: assets, defects, observations, routes (LINESTRING).
- В DTO наблюдений/активов lon/lat добавляются сериализаторами
  (`serializers.py::lonlat`), а не отдают сырой `WKTElement`.

## Политика «нет GPS — нет координат» (never fabricate)

`GeolocationService` (`services/geolocation.py`) выводит локацию кадра из
GPS-трека `upload.metadata['gps_track']`:

| Условие | Статус | Точка | Confidence |
|---------|--------|-------|-----------|
| трека нет | `UNAVAILABLE` | нет | — |
| зазор до ближайшей точки ≤ 2 c (`CONFIRMED_MAX_GAP_S`) | `CONFIRMED` | есть | 1.0 |
| зазор ≤ 10 c (`INTERPOLATED_MAX_GAP_S`), есть точки до/после | `ESTIMATED` (интерполяция) | есть | 0.6 |
| зазор ≤ 10 c, интерполяция невозможна | `ESTIMATED` (ближайшая) | есть | 0.4 |
| зазор > 10 c | `UNAVAILABLE` | нет | — |

**Accuracy gate (0.2.0, GEO-3):** если у точки трека указан `accuracy_m` хуже
`GPS_MAX_ACCURACY_M` (по умолчанию 50 м), статус понижается до `ESTIMATED`
даже при малом зазоре — точка с погрешностью в сотни метров не может быть
`CONFIRMED` при радиусах дедупликации 8–25 м. Отсутствие `accuracy_m` в
метаданных сохраняет прежнее поведение (backward compat). Невалидные
(не finite) значения `accuracy_m`/`heading_deg`/`speed_mps` делают точку
невалидной (считается в `invalid_points`, не используется).

**Naive timestamps — политика assume-UTC (0.2.0, GEO-1):** ISO-timestamps
GPS-трека и `capture_started_at` без `Z`/offset (типичный экспорт устройств)
нормализуются как **UTC** (`parse_track`, разрешение стартового времени).
Ранее naive datetime вступал в арифметику с aware и валил весь job
(TypeError на каждом кадре). Смешанные треки (naive + aware) также
обрабатываются без исключений. Политика осознанная: устройства пишут локальное
время без зоны, но для интерполяции важна согласованность шкалы; UTC —
единственный разумный дефолт. Если источник пишет в другой зоне — передавайте
timestamps с явным offset.

- Невалидные точки трека **считаются, но не используются** (`parse_track`,
  `invalid_points`); источник `UNKNOWN` при отсутствии данных.
- Инвариант `GeoObservation` (`models.py:60-70`): CONFIRMED/ESTIMATED обязаны
  иметь точку; UNAVAILABLE/INVALID — **не имеют**.
- CHECK в БД (`location_matches_status`) гарантирует согласованность на уровне схемы.
- Система **никогда не выдумывает** координаты: без GPS — `UNAVAILABLE`,
  объект остаётся в реестре без локации (`assets_without_location` в аналитике).

## Детекция перепутанных координат (swap detection)

`validate_coordinates` (`domain/geospatial/models.py:21-28`) проверяет диапазоны
и распознаёт типичную ошибку «широта/долгота перепутаны местами»:

```python
if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
    if -90 <= longitude <= 90 and -180 <= latitude <= 180 and abs(latitude) > 90:
        raise CoordinateError(
            f"Invalid coordinates (lon={longitude}, lat={latitude})",
            hint="coordinates_appear_swapped: expected (longitude, latitude)",
        )
    raise CoordinateError("Coordinates out of range ...")
```

Если значение «широты» выходит за ±90, а при перестановке обе величины попали бы
в допустимые диапазоны — выбрасывается `CoordinateError` с подсказкой
`coordinates_appear_swapped`. Это явная ошибка вместо молчаливого приёма
невалидных координат. `GeoPoint.__post_init__` вызывает валидацию автоматически.

### Слепое пятно: swap «оба значения в диапазоне» (GEO-4, честно)

Детекция выше ловит swap **только когда одно из значений выходит за допустимый
диапазон** (|lat| > 90). Если перепутанные значения **оба остаются в
диапазонах** — например `(55.75, 37.61)` вместо `(37.61, 55.75)` для Москвы —
ошибка **не детектируется**: точка формально валидна и молча попадает в реестр
(в случае Москвы — в Африку/океан или другую часть суши). Это фундаментальное
ограничение диапазонной валидации, а не баг.

Возможная mitigation (будущее, не реализовано): sanity-check против области
съёмки — отклонять/помечать точки вне ожидаемого bbox маршрута/региона
эксплуатации (`DEMO_AREA_BBOX` или bbox загруженного трека). Решение требует
знания области эксплуатации и не может быть универсальным, поэтому отложено;
до его внедрения ответственность за порядок координат несёт источник данных
(контракт требует `(longitude, latitude)`).

## EXPLAIN ANALYZE: проверка использования GiST

Для поиска кандидатов рекомендуется убедиться, что планировщик использует
GiST-индекс (`ix_assets_location`), а не seq scan. Эквивалент запроса
`find_candidates` для точки `(37.6173, 55.7558)`, радиус 15 м, тип `telecom_well`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.id,
       ST_Distance(a.location, ST_GeogFromText('POINT(37.6173 55.7558)')) AS distance_m
FROM assets a
WHERE a.location IS NOT NULL
  AND a.asset_type = 'telecom_well'
  AND a.lifecycle_status = 'ACTIVE'
  AND ST_DWithin(a.location, ST_GeogFromText('POINT(37.6173 55.7558)'), 15.0)
ORDER BY ST_Distance(a.location, ST_GeogFromText('POINT(37.6173 55.7558)'))
LIMIT 50;
```

Ожидаемый план: `Index Scan using ix_assets_location` (условие `ST_DWithin`
раскрывается в index condition через GiST), затем сортировка по `ST_Distance`
и `Limit`. Признаки проблемы: `Seq Scan on assets` при большой таблице —
проверить наличие индекса, актуальность статистики (`ANALYZE assets;`) и
селективность фильтра `asset_type`/`lifecycle_status`.

> `ST_GeogFromText('POINT(lon lat)')` эквивалентен `WKTElement(..., srid=4326)`
> в коде; порядок координат — строго (longitude, latitude).

## Размерности кадров: лимиты и downscale (0.2.0)

Защита от memory bomb (аудит SEC-5) и политика хранения:

- **Probe до decode**: размерность изображения/видеокадра проверяется ДО
  полного decode (парсинг заголовка JPEG / свойства VideoCapture). Кадр
  больше `PROCESSING_MAX_IMAGE_PIXELS` (64 Мп) или со стороной больше
  `PROCESSING_HARD_MAX_FRAME_SIDE` (8192) отклоняется без аллокации памяти
  под пиксели.
- **Downscale для обработки**: кадр уменьшается до longest side ≤
  `PROCESSING_MAX_FRAME_SIDE` (4096); quality gate (в т.ч. Laplacian blur)
  считается на уменьшенном кадре.
- **Оригинал сохраняется**: в хранилище (`frames/`) попадает обработанный
  кадр; исходная загрузка (`uploads/`) не изменяется никогда.
- **bbox — в пикселях сохранённого кадра**: ML получает уменьшенный кадр и
  возвращает абсолютные пиксельные координаты относительно него; кропы
  вырезаются из того же сохранённого кадра. Пересчёт к исходному разрешению
  оригинала не выполняется.

## Точки расширения локализации

Заложены, но **не реализованы** в MVP (источники уже в enum `geolocation_source`):

- **Map matching** (`MAP_MATCHING`) — привязка трека к дорожной сети;
  подключается в `GeolocationService` (`services/geolocation.py`, docstring
  явно называет map matching и visual localization точками расширения).
- **Визуальная локализация** (`VISUAL`) — определение позиции по изображению.
- **Ручная локализация** (`MANUAL`) — уже частично используется: ручной PATCH
  location актива ставит `CONFIRMED` (`services/assets.py:78-86`).
- **Embedding similarity** для дедупликации — `EmbeddingSimilarityProvider`
  (`services/deduplication.py:32`) пока заглушка (`NotImplementedError`).

Расширение не требует изменения схемы: `geolocation_source`/`geolocation_status`
уже содержат зарезервированные значения, а `location` остаётся `GEOGRAPHY(POINT,4326)`.

## Связанные документы
- [Схема БД](schema.md) · [Доменная модель](../architecture/domain-model.md) ·
  [Поток данных](../architecture/data-flow.md) · [Обзор системы](../architecture/system-overview.md)
