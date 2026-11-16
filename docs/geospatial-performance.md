# Geospatial Performance — Revizor

Замеры и оптимизации карты. Методика: `frontend/scripts/map-perf.mjs`
(Playwright chromium, 1440×900, live-режим с моком `/map/*` на 5000 активов /
2000 дефектов / 3000 наблюдений). Запуск: `node scripts/map-perf.mjs`
(требует backend :8000 и dev/preview :5173).

## 1. Измеренные показатели

| Метрика | Значение | Комментарий |
|---|---|---|
| Load → map ready (с login, 5000 features) | ~5.8 с | включает навигацию/login; стиль+тайлы+data |
| Активов в source | 5000 | загружены в GeoJSON source |
| Rendered asset-points / clusters (zoom 12) | 0 / 51 | supercluster агрегирует 5000 → 51 кластер |
| Style layers | 61 | 49 basemap + 12 data |
| JS heap idle | 45 MB | |
| FPS idle (2D) | 60 | |
| 2D → 3D mode switch | ~287 мс | easeTo pitch, без пересоздания карты |
| JS heap 3D | 45 MB | без роста |
| FPS 3D rotation (headless SwiftShader) | ~8 | software WebGL, 611 extruded buildings |
| FPS 3D rotation без зданий (SwiftShader) | ~15 | подтверждает: buildings — основной cost |
| JS heap 3D + hexbin | 45 MB | без роста |
| FPS 3D + hexbin idle | 61 | |
| Vector tiles (первый viewport) | 7 запросов | transferSize.cross-origin не раскрыт |

## 2. Интерпретация

- **Clustering работает под нагрузкой**: 5000 активов → 51 кластер на обзорном zoom,
  число rendered-точек остаётся низким. Это главный механизм масштабирования.
- **Память стабильна** (45 MB) через idle → 3D → hexbin: утечек при переключении
  режимов и подключении deck.gl не наблюдается. Один WebGL-контекст на карту
  (interleaved deck делит контекст MapLibre; `map.remove()` при unmount).
- **Низкий FPS ротации в headless — ограничение среды, не кода**: chromium без GPU
  использует SwiftShader (software WebGL). Непрерывная перерисовка vector-тайлов +
  fill-extrusion 611 зданий в software даёт ~8 fps; idle — 60 fps. На hardware GPU
  эти операции аппаратно ускорены. Buildings — основной cost (без них ~15 fps).
- Mode switch быстрый (~287 мс), т.к. карта не пересоздаётся (меняются камера и
  visibility слоёв).

## 3. Реализованные оптимизации

1. **Viewport-based loading**: `moveend` → bbox в query map-слоёв; серверная
   фильтрация по viewport (`ST_Intersects`). `keepPreviousData` — карта не
   размонтируется при refetch (нет мигания LoadingState, нет пересоздания контекста).
2. **Clustering**: native supercluster (`clusterMaxZoom:13, clusterRadius:42`).
3. **Lazy loading**: MapLibre (chunk ~218 KB gzip), deck.gl (~232 KB gzip, только при
   hexbin), MapPage — отдельные lazy chunks. Стиль — статический JSON.
4. **Conditional fetching**: observations запрашиваются только при видимом слое/heatmap.
5. **Source updates без пересборки**: `GeoJSONSource.setData` обновляет данные без
   пересоздания слоёв/стиля.
6. **Один WebGL-контекст**: deck interleaved делит контекст MapLibre; raster fallback
   через `setStyle` на том же инстансе; SchematicMap (SVG) при отказе WebGL.
7. **Cleanup**: `map.remove()`, ResizeObserver disconnect, popup remove, deck
   `removeControl` + `map.off('idle')`, cancelAnimationFrame (stats), пауза
   walkthrough-таймера при `document.hidden`.
8. **feature-state selection** вместо пересборки selection-слоя для активов.

## 4. Ограничения и рекомендации

- Software WebGL (headless/без GPU) — worst case для 3D ротации; для production
  рекомендуется hardware acceleration. При слабом GPU пользователь может оставаться
  в 2D (полная функциональность).
- При росте данных beyond 5000 на viewport: серверный cap `MAP_MAX_FEATURES=5000`,
  clustering и bbox-filtering удерживают нагрузку; следующий шаг — vector tiles для
  активов (MVTLayer) или серверная агрегация, если потребуется.
- Fill-extrusion зданий: `minzoom:13`, height interpolate по zoom (плавное появление),
  opacity 0.92. Здания не рендерятся на обзорных zoom (<13).
- Terrain/DEM не подключён (Москва плоская) — нет дополнительной GPU-нагрузки.

## 5. Воспроизведение

```bash
cd frontend
node scripts/map-perf.mjs          # нагрузочный сценарий (5000 объектов)
node scripts/perf.mjs              # LCP/CLS/long-tasks (общий)
```

Скриншоты режимов: `docs/assets/geospatial/`. QA-сводка: `docs/geospatial-qa.md`.
