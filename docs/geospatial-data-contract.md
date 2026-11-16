# Geospatial Data Contract — Revizor

Соглашения о координатах, геометрии и геоданных между backend, адаптером и рендером.
Основано на фактическом контракте (`backend/app/schemas/geo.py`,
`contracts/openapi/openapi.json`) и RFC 7946.

## 1. Координатная система

- **CRS**: WGS84 (EPSG:4326). RFC 7946 подразумевает WGS84; CRS-member в GeoJSON не
  объявляется. В БД — PostGIS `GEOGRAPHY(POINT/LINESTRING, srid=4326)`.
- **Порядок координат**: строго `[longitude, latitude]` (RFC 7946). В UI-строке
  отображается `lat, lon` (`lib/format.ts:fmtCoord`) — намеренное human-readable
  представление, не путать с порядком в геометрии.
- **Рендер**: MapLibre проецирует WGS84 → Web Mercator (EPSG:3857) для отображения.
- **Высота**: отсутствует в данных Revizor. Третья координата Point не приходит и
  **не интерпретируется** как altitude. Высоты зданий берутся только из OSM-тайлов
  (`render_height`), не из данных активов. Equipment extrusion не делается.

## 2. Типы геометрии

| Сущность | Геометрия | Источник |
|---|---|---|
| Asset | Point | GPS-трек / ручной PATCH |
| Observation | Point | GPS-трек (интерполяция по времени кадра) |
| Defect | Point (наследует Asset) | своей геометрии нет |
| Route | LineString | клиентский GPS-трек (2–10000 точек) |

Контракт (`geo.py`) поддерживает только Point и LineString. MultiPoint/Polygon/
MultiLineString/MultiPolygon в доменной модели не используются — поддержка не
добавлялась ради формальности. Адаптер отклоняет неподдерживаемые типы
(`unsupported_type`), не пытаясь их отрендерить.

## 3. Валидация и нормализация (frontend `geo/validate.ts`)

- `validatePosition([lon,lat])`: finite numbers, lon∈[−180,180], lat∈[−90,90].
- Swap-эвристика: |lat|>90 при |lon|≤90 → `swapped_coordinates` (отклоняется).
  In-range swap (Москва 55.75/37.61) эвристикой не ловится — документированный
  blind spot GEO-4 backend; frontend не пытается угадывать.
- LineString: ≥2 валидных точек; каждая точка валидируется.
- Отсутствующая геометрия (`null`) → `missing_geometry`, объект исключается из слоя.
- Невалидные координаты → `invalid_geometry`. Никаких координат «по умолчанию»
  (центр карты и т.п.) не подставляется.

## 4. Внутренние типы (`geo/types.ts`)

```ts
type Longitude = number & { __brand: 'Longitude' };
type Latitude  = number & { __brand: 'Latitude' };
interface LngLat { lon: Longitude; lat: Latitude; }
interface GeoFeature {
  kind: 'assets'|'defects'|'observations'|'routes';
  id: string;                       // исходный id сущности, не теряется
  geometry: GeoJSON.Point | GeoJSON.LineString;  // нормализованная, 2D
  domain: Record<string, unknown>;  // исходные свойства API без изменений
  presentation: { color, ringColor, label };     // производные визуальные значения
}
```

Брендированные типы исключают случайную перестановку lon/lat в коде. Domain и
presentation разделены: визуальные значения не подменяют исходные свойства.

## 5. Feature properties (backend → adapter)

Точные поля — `backend/app/schemas/geo.py:114-243` и `docs/api/geospatial.md`.
Ключевые для карты:

- **Asset**: id, asset_type, display_name, current_condition/severity/priority,
  priority_band, geolocation_status, location_accuracy_m, lifecycle_status, last_observed_at.
- **Defect**: id, asset_id, asset_type, defect_type, severity, status,
  current_priority, first/last_detected_at.
- **Observation**: id, asset_id (nullable), object_type, condition_class,
  detector_confidence, review_status, dedup_result, observed_at, processing_job_id.
- **Route**: id, name, vehicle_id, started/finished_at, total_distance_m.

Adapter добавляет в render-FC поля `_kind`, `_color`, `_ring`, `_label`
(presentation), сохраняя все domain-поля. Панели читают domain; слои — `_color/_ring`.

## 6. Геолокация: статусы и точность

- `geolocation_status`: CONFIRMED / ESTIMATED / UNAVAILABLE / INVALID.
  Логика backend (`services/geolocation.py`): gap≤2с → CONFIRMED; accuracy>50м →
  ESTIMATED; gap≤10с → интерполяция ESTIMATED; иначе UNAVAILABLE.
- `location_accuracy_m` (метры) — у Asset и Observation. manual PATCH default 5м.
- **Неопределённость**: для ESTIMATED с accuracy>0 адаптер строит кольцо
  (`accuracyPolygon`, радиус = accuracy_m). CONFIRMED/UNAVAILABLE кольца не имеют.
- UNAVAILABLE исключается из map-слоёв backend; в реестре и паспорте доступен,
  координаты можно задать вручную.

## 7. Покрытие (`geo/coverage.ts`)

`/analytics/coverage` → сетка над `area_bbox`. Формула ячеек повторяет backend
(`application/services/analytics.py:132-141`): equirectangular approximation,
`cell_lat = cell_m/111320`, `cell_lon = cell_m/(111320·cos(mid_lat))`, индексы
`(cx,cy)` от `min_lon/min_lat`. Coverage — эвристика обследования, не road-network
модель (честная оговорка backend). Ячейки геопривязываются на клиенте, цвет — по
числу наблюдений.

## 8. Топология

Asset-to-Asset связей в backend **нет** (нет таблицы топологии/parent/cable).
`cable_line` — Point-тип, не линия. Единственные реальные связи: Asset↔Observation↔
Defect, Route→Job→Observation, Defect M→N Observation. На карте рисуются только
треки маршрутов (реальная геометрия); фиктивные линии между активами не создаются.

## 9. Высоты зданий (basemap)

- Источник: OpenFreeMap vector tiles, схема OpenMapTiles, слой `building`.
- Атрибуты: `render_height`, `render_min_height` (метры). Значения из OSM-тегов
  `height`/`building:levels`; часть — оценка по этажам (не точный обмер).
- Проверено декодированием тайла Москвы z14: 700 зданий, медиана 18м, max 148м.
- Это высоты **зданий**, не оборудования. Активы размещаются на поверхности (z=0),
  визуальный offset не выдаётся за реальную высоту установки.

## 10. Лицензии и attribution

- Данные OSM: **ODbL**, attribution обязателен (MapLibre добавляет автоматически:
  OpenFreeMap © OpenMapTiles © OpenStreetMap).
- OpenFreeMap сервис: MIT; схема OpenMapTiles: BSD; MapLibre: BSD-3; deck.gl: MIT.
- Esri fallback raster: attribution © Esri · HERE · Garmin · FAO · NOAA · USGS.
- Self-host опция: PMTiles/Btrfs дампы OpenFreeMap (offline ≤3000 тайлов/50MB на запрос).
