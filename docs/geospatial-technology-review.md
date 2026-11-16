# Geospatial Technology Review — Revizor (Phase 1)

Дата: 2026-11-16. Сравнение движков и источников данных для геопространственной
подсистемы. Проверки выполнялись против фактического стека Revizor (React 18, Vite 6,
MapLibre GL JS 4.7.1, тёмная дизайн-система `frontend/src/styles/tokens.css`) и live
запросами к тайловым сервисам из среды разработки.

## 1. Движки

### 1.1 MapLibre GL JS — ВЫБРАН (базовый движок, уже в стеке)

- **Назначение**: 2D vector maps, камера pitch/bearing, fill-extrusion (3D здания),
  terrain/hillshade, custom layers, GeoJSON sources, feature-state, interaction events.
- **Преимущества**: уже установлен (4.7.1, `frontend/package.json`); весь существующий
  код карты (`MapView.tsx`, `SchematicMap.tsx`, 5 mount points) сохраняется; нативные
  clustering (supercluster), heatmap layer, expressions, `queryRenderedFeatures`;
  WebGL1 + WebGL2 (v5 — только WebGL2, поэтому **остаёмся на 4.7.1** ради fallback);
  миграция не нужна — 3D включается камерой и fill-extrusion поверх векторного источника.
- **Ограничения**: нет встроенной hexagon-агрегации; сложные data-driven визуализации
  (миллионы точек, GPU-агрегации) требуют deck.gl; стиль — декларативный JSON.
- **Сложность внедрения**: низкая (движок уже интегрирован).
- **Производительность**:   GPU-рендер, vector tiles загружаются по viewport; проверено e2e
  (`robustness.spec.ts:126-135` — реальные tile-запросы).
- **Внешние зависимости**: только тайловый источник (см. §2).
- **Лицензия**: BSD-3-Clause.
- **Совместимость**: полная (текущий стек).

### 1.2 deck.gl — ВЫБРАН (дополнительно, lazy-chunk)

- **Назначение**: GPU-агрегации и продвинутая геовизуализация: ScatterplotLayer,
  GeoJsonLayer, PathLayer, LineLayer, HeatmapLayer, **HexagonLayer**, IconLayer, MVTLayer.
- **Интеграция**: `@deck.gl/maplibre` → `MapLibreOverlay` (поддержка MapLibre v4.5.1+/v5/v6,
  подтверждено официальной документацией deck.gl). Режим **interleaved: true** вставляет
  deck-слои в стиль MapLibre и **делит его WebGL2-контекст** (один контекст на карту,
  корректная глубина с fill-extrusion зданиями; `beforeId` управляет порядком под подписи).
  Overlaid-режим (отдельный canvas) не используется — избегаем второго WebGL-контекста.
- **Преимущества**: HexagonLayer/HeatmapLayer для плотности дефектов/наблюдений
  (Phase 8); агрегация на GPU; те же данные/идентификаторы через общий store.
- **Ограничения**: +~200 KB gzip (lazy `import()` только при включении advanced-режима);
  требует WebGL2 для interleaved (при WebGL1 — деградация к нативным слоям MapLibre);
  собственный event-пайкинг нужно синхронизировать с MapLibre selection.
- **Сложность**: средняя (один overlay-компонент + синхронизация камеры/выбора).
- **Лицензия**: MIT.
- **Совместимость**: React 18 без обёрток (vanilla `MapLibreOverlay` как IControl),
  Vite manual chunk `deck`.

### 1.3 CesiumJS — ОТКЛОНЁН

- **Назначение**: глобус 3D, 3D Tiles (photogrammetry, BIM), terrain, glTF, 2D/2.5D/3D.
- **Почему нет**: в данных Revizor **нет 3D Tiles, фотограмметрии, инженерных моделей**;
 единственный 3D-контент — городские здания, которые полностью покрываются fill-extrusion
  MapLibre. Cesium — отдельная архитектура (свой рендер-луп, ion-токены для дефолтных
  ассетов, ~несколько MB bundle), дублирующий функциональность без пользы для задачи
  инспекции инфраструктуры. Лицензия Apache-2.0, но Cesium ion assets — проприетарные.
- **Когда пересмотреть**: при появлении реальных 3D Tiles обходов/фотограмметрии.

### 1.4 ArcGIS Maps SDK for JavaScript — ОТКЛОНЁН

- Проприетарная лицензия (требует apiKey/portal), vendor lock-in, тяжёлый bundle,
  платные сервисы для production-нагрузок. Не соответствует принципу открытых
  источников данных проекта. Функционально избыточен для задачи.

### 1.5 Three.js — ОТКЛОНЁН (на текущем этапе)

- **Назначение**: кастомные WebGL-сцены, glTF-модели оборудования, custom layer MapLibre.
- **Почему нет**: у Revizor **нет 3D-моделей оборудования и нет высот установки**
  (аудит §5: altitude отсутствует). Любой extrusion/offset активов был бы выдуманной
  высотой — запрещено требованиями (Phase 3/5). Реальная необходимость появится только
  с появлением glTF-паспортов оборудования; тогда — точечный custom layer, не замена движка.
- Лицензия MIT; сложность высокая (ручная геопривязка, освещение, picking).

## 2. Источники данных

### 2.1 OpenFreeMap — ВЫБРАН (основной basemap)

- **Что**: бесплатные vector tiles схемы OpenMapTiles (Planetiler), публичный инстанс
  `https://tiles.openfreemap.org`, без регистрации/ключей/лимитов запросов;
  еженедельные planet-дампы (Btrfs/MBTiles/**PMTiles**) для self-host.
- **Проверено live из среды разработки**:
  - TileJSON `https://tiles.openfreemap.org/planet`: tiles
    `…/planet/{version}/{z}/{x}/{y}.pbf`, minzoom 0, **maxzoom 14** (overzoom >14 —
    стандартный MapLibre), attribution OpenFreeMap © OpenMapTiles © OpenStreetMap.
  - Декодирование реального тайла Москвы z14 (9904/5121, центр 37.6173/55.7558):
    слой `building`, **700 features, у всех render_height>0**; медиана 18 м, max 71 м;
    соседние тайлы: max 148 м. Атрибуты `render_height`/`render_min_height` — реальные
    данные OSM (`height`, `building:levels`); часть высот — оценка по этажам
    (фиксируется в data-contract, не выдаётся за точный обмер).
  - Стили `fiord`/`dark` доступны (47 слоёв, building fill minzoom 12, glyphs
    `…/fonts/{fontstack}/{range}.pbf`). Кастомный стиль хостим сами (style JSON в
    `frontend/public/styles/`) — требование OpenFreeMap для модифицированных стилей.
- **Лицензии**: сервис MIT; данные OSM **ODbL** (attribution обязателен, MapLibre
  добавляет автоматически); схема OpenMapTiles BSD. Коммерческое использование разрешено.
  Offline-скачивание ≤3000 тайлов/50 MB за запрос (ToS) — для production рекомендуется
  self-host PMTiles-дампа.
- **Риски**: публичный инстанс без SLA → Esri raster fallback (уже в коде) +
  документированный путь self-host.

### 2.2 Esri World Dark Gray raster — СОХРАНЁН как fallback

- Текущий источник (`MapView.tsx:33-58`), проверен live (HTTP 200). Бесплатный
  публичный сервис, attribution © Esri · HERE · Garmin · FAO · NOAA · USGS.
  Растровый — 3D зданий не даёт; используется при недоступности векторных тайлов.

### 2.3 OpenStreetMap / OpenMapTiles / MapTiler / PMTiles / custom server

| Источник | Роль | Лицензия/условия |
|---|---|---|
| OSM | первоисточник данных (здания, высоты) | ODbL, attribution |
| OpenMapTiles | схема векторных тайлов (building: render_height/render_min_height) | BSD (схема), данные ODbL |
| MapTiler | альтернативный коммерческий хостинг + terrain-тайлы | API-ключ, free-tier лимиты; **не выбран** (ключи не нужны) |
| PMTiles | single-file архив тайлов для self-host (OpenFreeMap дампы) | MIT (формат); данные ODbL |
| Custom vector server | Planetiler/Tegola при self-host | open-source; не требуется на текущем этапе |

### 2.4 DEM / terrain — ПРОПУЩЕН (осознанное решение)

- Москва плоская (перепады <100 м на район инспекции); рельеф не улучшает задачу
  осмотра колодцев/шкафов/опор. Подключение DEM добавило бы внешний источник
  (MapTiler Terrain RGB — ключ; AWS Terrarium — Mapzen/Tilezen, SRTM/ODbL-совместимые
  данные) и GPU-нагрузку без пользовательской пользы.
- Решение соответствует требованию Phase 5 «не добавляй рельеф, если он не улучшает
  пользовательскую задачу». Hillshade/terrain можно включить позже одним source+layer.

### 2.5 OGC 3D Tiles — нет данных

- В Revizor отсутствуют 3D Tiles/фотограмметрия; подключение не обосновано (см. Cesium).

## 3. Итоговый стек (минимальный обоснованный)

```
MapLibre GL JS 4.7.1 (существующий)      — базовый движок 2D/3D, одна карта
  + OpenFreeMap vector (custom dark style, self-hosted JSON)
  + fill-extrusion buildings (render_height/render_min_height)
  + Esri raster fallback (существующий)
deck.gl 9.x (@deck.gl/maplibre, @deck.gl/layers, @deck.gl/aggregation-layers)
  — lazy chunk, interleaved MapLibreOverlay, HexagonLayer/HeatmapLayer
```

Не подключаются: CesiumJS, ArcGIS SDK, Three.js, terrain/DEM. Один WebGL-контекст на
карту (interleaved). Существующий SchematicMap SVG-fallback сохраняется для no-WebGL.

## 4. Стоимость миграции vs польза

Движок **не меняется** (MapLibre уже обеспечивает всё необходимое). Изменения:
источник тайлов (raster→vector+fallback), стиль (inline→self-hosted JSON), камера
(включение pitch/bearing), новые слои. Существующий 2D-сценарий оператора и контракт
`NetworkMap` сохраняются; риск минимален, польза — реальные 3D здания города и
производительный viewport-loading.
