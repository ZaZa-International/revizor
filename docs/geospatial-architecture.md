# Geospatial Architecture — Revizor

Целевая архитектура геопространственной подсистемы. Реализована в frontend
(`src/geo/`, `src/components/map/`, `src/app/MapPage.tsx`, `src/demo/walkthrough.tsx`)
поверх существующего backend geo-API. ONE CITY. ONE MAP. MULTIPLE DIMENSIONS.

## 1. Принципы

1. **Одна карта, несколько режимов.** 2D и 3D — режимы одного инстанса MapLibre,
   а не разные приложения. Переключение меняет камеру и видимость слоёв зданий,
   но не пересоздаёт карту, не сбрасывает selection и фильтры.
2. **Единый источник истины — URL.** Состояние карты сериализуется в query-параметры
   (`geo/state.ts`). Карта, боковые панели, фильтры и реестр читают одно состояние.
   Deep-link и reload восстанавливают режим, камеру, слои, фильтры и выбранный объект.
3. **Адаптер между API и рендером.** API-ответы не попадают в библиотеку визуализации
   напрямую. `geo/adapter.ts` валидирует геометрию, нормализует координаты, отделяет
   domain-данные от presentation-свойств. Исходные id и свойства сохраняются.
4. **Только подтверждённая география.** Нет выдуманных координат, высот и топологии.
   Объекты без GPS исключаются из слоёв; неопределённость показывается кольцом accuracy;
   здания используют реальные `render_height` OSM; связи между Asset не рисуются
   (в backend нет таблицы топологии).

## 2. Слои

```
┌─ MapPage.tsx (оркестрация) ──────────────────────────────────────────────┐
│ useMapState() ── URL: mode/view/cam/layers/filters/selected/from/to       │
│ useMapAssets/Defects/Observations/Routes (bbox viewport, keepPreviousData)│
│ useCoverage (сетка /analytics/coverage)                                   │
│ useWalkthrough (demo-сценарий)                                            │
├───────────────────────────────────────────────────────────────────────────┤
│ geo/state.ts      — parse/serialize MapState, useMapState (URL sync)      │
│ geo/adapter.ts    — API FC → GeoFeature[] → render FC (+presentation)     │
│ geo/validate.ts   — RFC 7946, диапазоны, swap, accuracyPolygon            │
│ geo/coverage.ts   — геопривязка сетки покрытия (формула backend)          │
│ geo/palette.ts    — семантические цвета (токены дизайн-системы)           │
│ geo/types.ts      — branded Longitude/Latitude, GeoFeature, MapCamera     │
│ geo/deck.ts       — lazy deck.gl HexagonLayer (interleaved)               │
├───────────────────────────────────────────────────────────────────────────┤
│ components/map/NetworkMap.tsx — WebGL pre-check → MapView | SchematicMap  │
│ components/map/MapView.tsx    — MapLibre: style, sources, layers, camera  │
│ components/map/DeckOverlay.tsx— lazy-обёртка deck.gl поверх карты         │
│ components/map/inspection.tsx — Asset/Observation/Defect/Route панели     │
│ components/map/SchematicMap.tsx — SVG fallback (без WebGL)                │
│ demo/walkthrough.tsx          — 10-шаговый DEMO-сценарий                  │
└───────────────────────────────────────────────────────────────────────────┘
Backend (без изменений контракта, additive fixes):
  /api/v1/map/{assets,defects,observations,routes} — GeoJSON [lon,lat] WGS84
  /api/v1/analytics/coverage, /assets/{id}/{history,observations,defects}
```

## 3. Единое состояние карты (`geo/state.ts`)

```ts
MapState {
  mode: '2d' | '3d';
  view: 'network' | 'infrastructure';
  camera: { center:[lon,lat], zoom, pitch, bearing } | null;  // null = fit to data
  layers: { assets, defects, observations, routes, coverage, heatmap, hexbin };
  filters: { asset_type, priority_band, defect_status, severity_min };
  selection: { layer: GeoKind, id } | null;
  timeRange: { from, to };   // observed_at, ISO date
}
```

URL-параметры: `mode`, `view`, `cam=z,lon,lat,pitch,bearing`, `layers=<csv enabled>`,
`asset_type`, `priority_band`, `defect_status`, `severity_min`, `selected`, `layer`,
`from`, `to`. Лишние параметры (напр. `stats=1`) сохраняются.

- `useMapState()` хранит `paramsRef` и синхронно мержит патчи — несколько вызовов
  `update()` в одном тике композируются (react-router `setSearchParams` не композирует
  функциональные апдейты сам).
- Дефолты зависят от view: `infrastructure` включает observations и coverage.
- Переключение mode меняет только mode/camera — selection/filters сохраняются.

## 4. Geospatial data adapter (`geo/adapter.ts`)

- `adaptCollection(kind, fc)` → `{ features: GeoFeature[], rejected: RejectedFeature[], render: FC }`.
- Валидация (`geo/validate.ts`): порядок `[lon,lat]`, диапазоны lon∈[−180,180],
  lat∈[−90,90], swap-эвристика (|lat|>90 при |lon|≤90), LineString ≥2 точек.
  Третья координата **не интерпретируется как высота** (высот в данных нет).
- `GeoFeature.domain` — исходные свойства API без изменений (id, severity, confidence…).
  `GeoFeature.presentation` — производные визуальные значения (color, ringColor, label).
  В render-FC они добавляются полями `_kind/_color/_ring/_label`, **не затирая** domain.
- Невалидная/отсутствующая геометрия → `rejected` (с причиной), в карту не попадает
  и не подменяется выдуманными координатами.
- `accuracyCollection()` — кольца неопределённости только для ESTIMATED с
  `location_accuracy_m>0` (полигон радиуса accuracy в метрах → градусы).
- `boundsOf`, `findFeature`, `selectionCollection`, `featurePosition` — общие хелперы.

## 5. Рендер (`MapView.tsx`)

- Basemap: self-hosted vector style `public/styles/revizor-dark.json` (графитовый
  restyle OpenFreeMap fiord, генератор `scripts/build-map-style.mjs`). Источник
  `openmaptiles`, glyphs OpenFreeMap. Fallback: Esri raster (при >8 tile-errors),
  затем SchematicMap SVG (при отказе WebGL / повторных ошибках).
- 3D здания: слой `building-3d` (fill-extrusion, `render_height`/`render_min_height`,
  minzoom 13, interpolate по zoom). В 2D виден плоский `building`, в 3D — extrusion.
  Подписи (symbol) выше зданий и data-слоёв (`beforeId` = первый symbol).
- Data-слои: coverage-cells/outline, routes-line, obs-heatmap (native), obs-points,
  accuracy-fill/line, asset-clusters/count/points (supercluster, promoteId:'id'),
  defect-rings, selection-ring. Выделение актива — feature-state `selected`
  (плавный radius/stroke через `-transition`).
- Камера: `moveend` эмитит camera+bbox только для пользовательских движений
  (`originalEvent`) или ожидаемых программных (`expectMove`), не для `resize`.
  Это предотвращает перезапись URL stale-камерой.
- `fitToData` один раз при первом непустом наборе (если камера не восстановлена из URL).
- `onMapReady` отдаёт инстанс карты для DeckOverlay; `__revizorMap` на контейнере — для QA.
- Cleanup: `map.remove()`, ResizeObserver disconnect, popup remove, deck dispose.

## 6. deck.gl (`geo/deck.ts`, `DeckOverlay.tsx`)

- Грузится динамически только при включении `hexbin`. `MapLibreOverlay` interleaved —
  общий WebGL2-контекст с MapLibre (один контекст на карту). HexagonLayer дефектов
  (цвет по severity, extrusion в 3D), `beforeId` под подписи, `pickable:false`
  (selection остаётся на MapLibre-слоях, без конфликта событий).
- `setProps({interleaved:true, layers})` — interleaved передаётся каждый раз
  (иначе deck сбрасывает режим). `ensure` на `map.on('idle')` добавляет layer-group,
  если стиль ещё не был загружен в момент первого `setProps`.
- WebGL1 → overlay не создаётся, toast «требует WebGL2»; native heatmap доступен всегда.

## 7. Viewport-loading и производительность

- `moveend` → `onViewportChange(bbox)` → `bbox` в query map-слоёв (контракт поддерживает).
  `keepPreviousData` — карта не размонтируется при refetch (нет мигания LoadingState).
- Observations запрашиваются только при видимом слое/heatmap (`enabled`).
- Clustering (supercluster) держит число rendered-точек низким при большом наборе.
- Lazy chunks: maplibre, deck, MapPage. Стиль — статический JSON.
- Замеры и методика: `docs/geospatial-performance.md`.

## 8. Inspection (`inspection.tsx`)

- Asset: вкладки Обзор / Наблюдения / Дефекты / История / Сравнение. Accuracy,
  кольцо неопределённости, timeline истории (`is_physical_change`), сравнение двух
  последних объездов (исходные ML-предсказания + решение оператора раздельно).
- Observation: кадр (permission-gated), координаты/accuracy/источник, confidence модели,
  severity ML, review_status, effective_*; подтверждение оператором (явный клик,
  `usePermissions` учитывает demo-режим).
- Defect: severity/status/даты, связь с Asset, observation_count.
- Confidence ≠ severity ≠ priority — раздельные поля, отсутствующие значения «—».

## 9. Demo Walkthrough (`demo/walkthrough.tsx`)

10 шагов на demo-fixtures (asset с `is_physical_change`): 3D района → объекты →
дефекты → приближение → паспорт → наблюдение → сравнение → физическое изменение →
подтверждение оператором (явный клик, demo-мутация) → история. Play/pause/next/prev/exit,
авто-пауза при `document.hidden`, шаг 9 ждёт действия. Exit восстанавливает snapshot
состояния. Всё маркировано DEMO; реальные данные не изменяются.

## 10. Границы и gaps (не реализовано намеренно)

- Высоты оборудования, Asset-to-Asset топология, 3D-модели, DEM — отсутствуют в
  данных; не выдумываются. См. `docs/geospatial-audit.md` §13.
- Terrain пропущен (Москва плоская) — `docs/geospatial-technology-review.md` §2.4.
