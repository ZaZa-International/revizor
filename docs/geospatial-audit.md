# Geospatial Audit — Revizor (Phase 0)

Дата: 2026-11-16. Аудит фактического кода (не документации). Все ссылки — `file:line`
на момент аудита. Область: frontend-карта, backend geo-API, геомодель, контракты, тесты.

## 1. Текущая архитектура карты

```
┌─ React 18 + Vite 6 + TanStack Query 5 (без state-библиотек) ─────────────┐
│ MapPage.tsx ── useMapAssets/Defects/Observations/Routes (hooks.ts)       │
│      │            │ demo: src/demo/provider.ts (локальные FeatureColl.)  │
│      │            │ live: openapi-fetch → /api/v1/map/* (schema.d.ts)    │
│      ▼            ▼                                                      │
│ NetworkMap.tsx ── WebGL pre-check ── нет → SchematicMap.tsx (SVG)        │
│      │ есть                                                              │
│      ▼ lazy()                                                            │
│ MapView.tsx ── MapLibre GL JS 4.7.1, raster Esri Dark Gray, strictly 2D  │
│      sources: assets(cluster)/defects/observations/routes/selection      │
│      setData(FeatureCollection verbatim) — адаптера нет                  │
└──────────────────────────────────────────────────────────────────────────┘
Backend: FastAPI → GeospatialService → PostGIS GEOGRAPHY(4326) → shapely.mapping
```

- Движок: **MapLibre GL JS 4.7.1** (`frontend/package.json`). Leaflet/OpenLayers/deck.gl/three/cesium отсутствуют.
- Точки монтирования `NetworkMap` (5): `MapPage.tsx:160`, `OverviewPage.tsx:157-167`,
  `AssetPassportPage.tsx:158-167`, `RouteDetailPage.tsx:44-50`, `showcase/scenes/DigitalTwin.tsx:63-84`.
- Общий контракт пропсов: `assets/defects/observations/routes` (FeatureCollection|null),
  `visible: LayerVisibility`, `selectedId`, `onSelect(MapSelection)`.

## 2. Картографические библиотеки и тайлы

| Компонент | Факт | Ссылка |
|---|---|---|
| maplibre-gl | 4.7.1, manual chunk `maplibre` | `frontend/package.json`, `vite.config.ts:24-35` |
| Базовая карта | hardcoded raster style: Esri `World_Dark_Gray_Base` + `_Reference`, tileSize 256, maxzoom 16, без ключей/env | `MapView.tsx:33-58` |
| Glyphs | не заданы в стиле; cluster-count использует `['Open Sans Semibold']` (дефолтный glyph-endpoint MapLibre) | `MapView.tsx:157` |
| CRS рендера | Web Mercator (MapLibre default); данные WGS84 | `MapView.tsx:88-96` |
| 3D | отсутствует: `dragRotate:false, pitchWithRotate:false`, `touchZoomRotate.disableRotation()` | `MapView.tsx:94-95,102` |
| Terrain/hillshade | нет | — |

## 3. Data flow и endpoint'ы

Frontend hooks (`frontend/src/data/hooks.ts:473-526`), query keys `['map-*', mode, params]`,
staleTime 30s (routes 60s). Параметры, реально отправляемые `MapPage.tsx:27-31`:

| Endpoint | Query (факт UI) | Поддерживается контрактом | Response |
|---|---|---|---|
| `GET /api/v1/map/assets` | `asset_type`, `priority_band`, `limit:2000` | + `bbox` (**не используется UI**) | `FeatureCollection[AssetMapProperties]` |
| `GET /api/v1/map/defects` | `status`, `severity_min` | + `bbox` (**не используется**) | `FeatureCollection[DefectMapProperties]` |
| `GET /api/v1/map/observations` | `{}` (всегда, даже при скрытом слое) | + `bbox`, `job_id`, `date_from/to` | `FeatureCollection[ObservationMapProperties]` |
| `GET /api/v1/map/routes` | без параметров | только `limit` (1–1000) | `FeatureCollection[RouteMapProperties]` |
| `GET /api/v1/analytics/coverage` | — | grid 250 м над demo-bbox | `CoverageResponse` (SVG-график, не карта) |
| `GET /api/v1/assets/nearby` | **не используется ни одним hook** | lon/lat/radius_m ≤5000 | `NearbyAssetsResponse` |

Backend: `app/api/v1/map.py:28-176` → `app/application/services/geospatial.py:44-189`.
Cap `MAP_MAX_FEATURES=5000` (geospatial.py:26). GeoJSON строится в Python через
`shapely.mapping` (geospatial.py:29-33), не `ST_AsGeoJSON`. Серверной кластеризации нет.

## 4. Фактическая структура GeoJSON

Схемы: `backend/app/schemas/geo.py`. Координаты **[longitude, latitude]**, RFC 7946.
CRS-member не объявляется (RFC 7946 подразумевает WGS84); SRID 4326 — на уровне БД.
Геометрии контракта: **только Point и LineString** (geo.py:27-58).

Properties (geo.py:114-243):

- **AssetMapProperties**: id, asset_type, display_name, current_condition, current_severity,
  current_priority, priority_band, geolocation_status, location_accuracy_m, lifecycle_status, last_observed_at.
- **DefectMapProperties**: id, asset_id, asset_type, defect_type, severity, status,
  current_priority, first_detected_at, last_detected_at. Геометрия — точка Asset (geospatial.py:97-112).
- **ObservationMapProperties**: id, asset_id (nullable до dedup), object_type, condition_class,
  detector_confidence, review_status, dedup_result, observed_at, processing_job_id.
- **RouteMapProperties**: id, name, vehicle_id, started_at, finished_at, total_distance_m.

## 5. Координатные системы и качество геоданных

- Порядок `[lon, lat]` — везде в геометрии (`MapView.tsx:240-255`, `SchematicMap.tsx:61-68`,
  demo `provider.ts:529`). UI-строка отображает `lat, lon` намеренно (`lib/format.ts:68-71`,
  unit-тест `tests/lib.test.ts:23-25`).
- **Высоты нет**: ни altitude/elevation/Z у Asset/Observation/Route (grep по backend = 0).
  Точки строго 2D. Третья координата не приходит и не должна ожидаться.
- **GPS accuracy есть**: `location_accuracy_m` (Float, метры) у Asset (`models/asset.py:50`)
  и Observation (`models/observation.py:101`); `geolocation_status` CONFIRMED/ESTIMATED/
  UNAVAILABLE/INVALID; `geolocation_source` только у Observation (`observation.py:108-112`).
- Источник координат: **клиентский GPS-трек** в `upload.metadata.gps_track` + ручной PATCH.
  EXIF GPS extraction отсутствует (grep `getexif|piexif|exifread` = 0).
  Логика: `services/geolocation.py:120-185` — gap ≤2 с → CONFIRMED; accuracy >50 м → ESTIMATED;
  gap ≤10 с → интерполяция ESTIMATED; иначе UNAVAILABLE. Координаты не выдумываются.
- Swap-детекция: только при |lat|>90 (`domain/geospatial/models.py:21-28`); in-range swap
  (Москва 55.75/37.61) проходит молча — документированный blind spot GEO-4
  (`docs/api/geospatial.md:15-17`).
- DB CHECK `(location IS NULL) = (status IN UNAVAILABLE/INVALID)` (`asset.py:36-39`,
  `observation.py:55-58`); map-слои исключают null-location (geospatial.py:57,100,138).

## 6. Геометрии и топология

| Вопрос | Ответ | Evidence |
|---|---|---|
| Non-Point геометрии | Только Route LINESTRING (реальный клиентский трек, 2–10000 точек) | `models/route.py:26-28`, `schemas/routes.py:49-69`, `services/routes.py:39-47` |
| Asset-to-Asset связи | **НЕТ**. Таблиц топологии/parent/cable-connections не существует. `cable_line` — Point-тип в taxonomy | grep по `models/`; единственная M→N — `defect_observations` (`defect.py:27-41`) |
| Высоты зданий | В данных Revizor нет; доступны из OSM-тайлов (OpenMapTiles `render_height`) | см. technology-review |
| Рельеф/DEM | Нет в данных | grep |
| Временные метки | `observed_at`/`detected_at` (Observation), `first/last_observed_at` (Asset), `first/last_detected_at`/`resolved_at` (Defect), `started/finished_at` (Route) | `observation.py:82-83`, `asset.py:73-74`, `defect.py:67-69`, `route.py:24-25` |
| История Asset | **ЕСТЬ API**: `GET /assets/{id}/history` (append-only, `is_physical_change`), `/observations`, `/defects`, `/reviews?observation_id=` | `api/v1/assets.py:248-343`, `models/history.py:13-42` |
| Объём данных | demo seed: 15 assets (2 без GPS), 24 obs, 9 defects, 3 routes (`scripts/seed_demo.py`); live-БД на момент аудита: 22/37/20/3. Cap слоя 5000 | psql count, seed |

Связи сущностей: Asset 1—N Observation/Defect; Defect M—N Observation; Observation N—1
Job/JobFrame; Job N—1 Upload/Route; Review → Observation/Defect (append-only).
Дедупликация связывает observation→asset (score/explanation), route-контекст входит
в dedup через `ProcessingJob.route_id` (`domain/deduplication/policy.py:68-73`).

## 7. Слои, кластеризация, выбор (frontend)

- Sources/layers добавляются на `map.on('load')` (`MapView.tsx:113-201`):
  `routes-line` (line #3D8A81), `obs-points` (circle, match review_status),
  `asset-clusters` + `asset-cluster-count` (native supercluster: `cluster:true,
  clusterMaxZoom:13, clusterRadius:42`, `MapView.tsx:117`), `asset-points`
  (circle r7, match priority_band → BAND_COLORS `MapView.tsx:26-31`),
  `defect-rings` (кольцо r12, severity≥4 → crit, иначе warn, `MapView.tsx:187`),
  `selection-ring` (r15).
- Кластеризуется только assets; клик по кластеру → `getClusterExpansionZoom` + easeTo
  (`MapView.tsx:231-239`).
- Selection: единый `map.on('click')` → `queryRenderedFeatures` по interactive-слоям
  (`MapView.tsx:223-256`); пустой клик → `onSelect(null)`. Hover-popup только для
  asset-points (`MapView.tsx:214-221`).
- Видимость: `setLayoutProperty visibility` (`MapView.tsx:319-329`). Дефолт:
  observations выключены (`MapPage.tsx:21`), но запрос всё равно выполняется.
- fitBounds один раз при первом непустом наборе (`MapView.tsx:280-290,368-393`).
- Контекстные панели: левая `map-side` (слои/фильтры/легенда, `MapPage.tsx:94-154`),
  правая `map-context` (карточки asset/defect/observation/route + deep links,
  `MapPage.tsx:172-251`). Asset-карточка догружает `useAsset(id)` (`MapPage.tsx:33-34`).

## 8. Состояние и синхронизация

- URL: пишутся только `selected`/`layer` (`MapPage.tsx:48-59`); фильтры читаются при
  инициализации, но **не пишутся** при изменении. Камера не персистится.
- **Баг deep-link**: `/app/map?selected=X&layer=assets` (ссылка из паспорта,
  `AssetPassportPage.tsx:102`) рисует кольцо, но контекстная панель остаётся пустой —
  `selection` state = null до клика (`MapPage.tsx:25,166,173`).
- Persist: `localStorage['revizor.mode']` (live/demo, `data/source.tsx:15-23`),
  сессия `revizor.session` (`api/client.ts:14-41`). Map-state не сохраняется.

## 9. Обработка ошибок

- Нет координат: backend исключает из слоёв; UI — «нет координат» (`format.ts:68-71`),
  EmptyState в паспорте (`AssetPassportPage.tsx:105-111`); demo фильтрует null
  (`provider.ts:521,551,577`). Точка с неизвестными координатами в центр карты не ставится.
- Пустая выдача: `EMPTY` FeatureCollection (`MapView.tsx:60,312`), counts=0, EmptyState.
- Тайлы/WebGL — трёхуровневая деградация: pre-check (`NetworkMap.tsx:27-40`) →
  SchematicMap; throw конструктора → fallback (`MapView.tsx:87-100`); >8 tile-errors
  или `webglcontextlost` → fallback (`MapView.tsx:104-111`).
- API: ErrorState + request_id + retry (`ui.tsx:164-186`), агрегированный баннер
  (`MapPage.tsx:61,87-91`), 401 → logout (`client.ts:77-83`).

## 10. Тесты (существующие)

- Unit (vitest, node-env): 28 тестов — `src/tests/lib.test.ts` (порядок координат,
  форматтеры, bbox), `src/tests/demo.test.ts` (детерминизм demo, форма map-слоёв
  `[lon,lat]`, фильтры, review-логика). **MapView/MapLibre-логика unit-тестами не покрыта.**
- E2E (Playwright, chromium 1440×900, baseURL :5173, demo-режим без backend): 42 теста.
  Map-релевантные: `app-demo.spec.ts:30-39` (поверхностно), `app-live.spec.ts:43-55`
  (@live, требует backend), `robustness.spec.ts:10-42` (no-WebGL → SVG + выбор объекта;
  abort Esri tiles), `:126-135` (реальные tile-запросы), `responsive.spec.ts:81-92`
  (mobile 390: canvas над панелями). QA-скрипты: `scripts/visual-qa.mjs`, `scripts/perf.mjs`.

## 11. Проблемы текущей реализации

1. Нет viewport-loading: статический `limit:2000`, `bbox` не отправляется (контракт поддерживает).
2. Частичная URL-синхронизация + баг deep-link панели (§8).
3. Легенда «кольцо — дефект S3+» (`MapPage.tsx:146`) vs код `severity>=4` (`MapView.tsx:187`).
4. Cluster-count font без glyphs в стиле (`MapView.tsx:157`).
5. Mini-maps over-fetch: 500 assets ради подсветки одного (`AssetPassportPage.tsx:159`).
6. Observations запрашиваются даже при выключенном слое (`MapPage.tsx:21,30`).
7. GeoJSON отдаётся в рендер verbatim — нет валидации/нормализации/адаптера.
8. Map-e2e поверхностные для WebGL-пути; нет unit на syncData/selection/fitBounds.
9. Строго 2D: pitch/bearing/rotation отключены; векторного basemap нет.
10. `/assets/nearby` не используется.

## 12. Расхождения контракт/код (backend)

1. `map_routes` description обещает «без трека → geometry=null», фактически такие
   маршруты **исключаются** (`geospatial.py:171` vs `map.py:164-165`).
2. «Выборка детерминирована» (`map.py:44`), но ORDER BY есть только у observations
   (`geospatial.py:147`); assets/defects/routes — без сортировки → усечение недетерминировано.
3. PATCH /assets description обещает `geolocation_source=MANUAL`, но у Asset нет колонки
   source (`services/assets.py:93-95`).
4. OpenAPI examples defect/observation/route FeatureCollection копируют asset-example
   (`schemas/geo.py:79-106`).
5. `docs/database/schema.md` устарел после `0002_hardening` (FK RESTRICT, partial uniques,
   ml_response, request_hash, frames_sum).

## 13. План развития

См. `docs/geospatial-architecture.md` (целевая архитектура) и
`docs/geospatial-technology-review.md` (выбор стека). Кратко:

- **Без изменений backend**: векторный basemap OpenFreeMap + 3D buildings (реальные
  `render_height`), 2D/3D режимы одной карты, единое состояние + URL-sync, геоадаптер,
  viewport bbox-loading, infrastructure view, coverage-геопривязка сетки
  `/analytics/coverage`, time-slider (date_from/to уже есть), inspection-панель
  (history/observations/defects hooks уже есть), deck.gl агрегации, demo walkthrough,
  кольцо GPS-неопределённости (accuracy уже в properties).
- **Минимальные additive backend fixes** (согласовано): ORDER BY в map-слоях
  (детерминированность), `bbox`/`date_from/to` для `/map/routes`, исправление
  description расхождений. Миграции не требуются.
- **Требует новых геоданных (НЕ делаем, документируем gap)**: высоты оборудования
  (нет источника → никакой extrusion активов), Asset-to-Asset топология (нет таблицы →
  связи не рисуются), 3D-модели оборудования (нет glTF), DEM (Москва плоская — не нужен),
  AuditLog read-API (история покрывается `/assets/{id}/history`).
