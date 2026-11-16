# Geospatial QA — Revizor

Сводка проверок геопространственной подсистемы. Все прогоны выполнены локально
против реальных PostgreSQL/PostGIS + Redis + S3 (docker) и dev-сервера frontend.
Скриншоты: `docs/assets/geospatial/`.

## 1. Команды и результаты

| Набор | Команда | Результат |
|---|---|---|
| Backend lint/format | `uv run ruff check . && uv run ruff format --check .` | PASS |
| Backend types | `uv run mypy app` | PASS (137 files) |
| Backend unit | `uv run pytest -m unit` | 256 passed |
| Backend full (integration/api/contract, реальные сервисы) | `uv run pytest` | **667 passed** |
| OpenAPI drift | `make openapi-check` | PASS (40 paths) |
| Frontend typecheck | `npm run lint` (`tsc -b --noEmit`) | PASS |
| Frontend unit | `npm test` (vitest) | **51 passed** |
| Frontend e2e (Playwright chromium) | `npx playwright test` | **56 passed** |
| Production build | `npm run build` | PASS (deck/maplibre lazy chunks) |
| Perf | `node scripts/map-perf.mjs` | см. `geospatial-performance.md` |

## 2. Feature table

| Feature | Status | Evidence |
|---|---|---|
| 2D карта (векторный basemap, слои, кластеры) | PASS | `map-geospatial.spec.ts` «2D: векторный basemap…»; `2d-map.png` |
| 3D buildings (реальные высоты OSM) | PASS | «2D → 3D: наклон, здания…»: pitch>40, building-3d visible, extrusions>0; `3d-city.png`, `3d-selected-asset.png` |
| Infrastructure layers (assets/obs/defects/routes/coverage) | PASS | «Infrastructure view: покрытие…»: coverage-cells visible, cells>0; `infrastructure-view.png` |
| Asset selection + инспекция | PASS | «2D → 3D… выбор не сбрасывается», «deep-link ?selected…»; `3d-selected-asset.png` |
| Defect selection | PASS | «выбор наблюдения и дефекта открывает инспекцию»; `selected-defect.png` |
| Observation selection + confidence/severity раздельно | PASS | тот же тест: «Confidence модели», «Карточка наблюдения»; `selected-observation.png` |
| Camera transitions 2D↔3D без сброса selection | PASS | «2D → 3D…»: selected сохраняется в URL и панели при обоих переключениях |
| Единое состояние / URL / reload | PASS | «фильтры пишутся в URL и сохраняются при 2D↔3D», «deep-link…» |
| Hexagon aggregation (deck.gl lazy, interleaved) | PASS | «гексагональная агрегация deck.gl подключается lazy»: layer-group attached; `hexbin-2d.png`, `hexbin-defects.png` |
| Demo Walkthrough (10 шагов, подтверждение, exit) | PASS | «демо-сценарий: запуск, пауза, шаги, подтверждение, выход»; `walkthrough-compare.png` |
| Responsive (360/390/768/1024/1440/1920) | PASS | `responsive.spec.ts` sweep (8 ширин, без overflow) + mobile map; `mobile-390-map.png` |
| WebGL fallback (no-WebGL → SVG) | PASS | `robustness.spec.ts` «отказ WebGL → интерактивная SVG-схема» |
| WebGL context lost → fallback | PASS | `map-failures.spec.ts` «потеря WebGL context → schematic fallback» |
| Tile failure → raster → schematic | PASS | `robustness.spec.ts` «отказ тайлов basemap → raster fallback → schematic» |
| API timeout / 503 → ErrorState + retry | PASS | `map-failures.spec.ts` «API 503…», «timeout сети…» |
| Некорректная/отсутствующая геометрия | PASS | unit `geo.test.ts` + e2e «некорректная геометрия отклоняется адаптером» |
| Пустая выдача | PASS | `map-failures.spec.ts` «пустая выдача слоёв → counts 0» |
| Performance (5000 объектов, память, FPS) | PASS | `scripts/map-perf.mjs`: 5000→51 кластер, heap 45MB стабильна, idle 60fps; см. оговорку SwiftShader в `geospatial-performance.md` |
| Backend map determinism + routes bbox/date | PASS | `tests/api/test_map_api.py` (11 тестов), contract tests |

## 3. Unit-покрытие геомодуля (`src/tests/geo.test.ts`, 23 теста)

- Валидация координат: порядок `[lon,lat]`, диапазоны, swap-эвристика, третья
  координата не интерпретируется как высота, LineString ≥2 точек.
- Адаптер: сохранение id/domain, presentation не затирает domain, reject
  missing/invalid/unsupported геометрии, цвета дефектов S4+/S1–3, null-коллекция.
- Кольца неопределённости: только ESTIMATED с accuracy>0, радиус в метрах.
- Покрытие: формула ячеек совпадает с backend, геопривязка (cx,cy).
- Состояние: дефолты, roundtrip mode/camera/layers/filters/selection/time,
  переключение 2D→3D сохраняет selection/фильтры, невалидная камера отклоняется,
  лишние URL-параметры сохраняются.

## 4. E2E-сценарии карты

`map-geospatial.spec.ts` (9): 2D basemap/кластеры/легенда S4+; 2D→3D здания +
сохранение выбора; deep-link панели; фильтры в URL + reload; Infrastructure view
(покрытие/наблюдения/период); выбор наблюдения и дефекта; deck.gl hexbin lazy;
демо-сценарий (10 шагов + подтверждение + exit); сброс камеры.

`map-failures.spec.ts` (5): API 503; пустая выдача; некорректная геометрия;
потеря WebGL context; timeout сети + retry. Live-тесты переиспользуют одну
сессию (storageState), чтобы не превышать backend rate-limit логина (10/мин per IP).

## 5. Failure scenarios (покрытие требований Phase 12)

| Сценарий | Покрытие |
|---|---|
| Тайлы недоступны | raster fallback → SVG (robustness) |
| API timeout / 503 | ErrorState + request_id + retry (map-failures) |
| Некорректная геометрия | adapter reject, карта жива (unit + e2e) |
| Отсутствующие координаты | missing_geometry reject, не центр карты (unit + e2e) |
| Нет WebGL | SVG-схема с выбором (robustness) |
| Потерян WebGL context | schematic fallback (map-failures) |
| Неизвестная высота | здания без height не extrude-ятся выдуманно; активы на z=0 (data-contract) |
| Пустая выдача | counts 0, EmptyState (map-failures) |

## 6. Responsive

`responsive.spec.ts`: sweep 360/375/390/768/1024/1280/1440/1920 по 8 страницам
(включая `/app/map`) — без горизонтального переполнения. Mobile 390: карта над
панелями (`order:-1`), компактный toolbar, walkthrough-панель адаптирована.
Скриншот: `mobile-390-map.png`.

## 7. Известные ограничения / честные оговорки

- **FPS 3D ротации в headless ~8** — software WebGL (SwiftShader) без GPU; idle 60fps,
  память стабильна. На hardware GPU операции аппаратно ускорены. Buildings — основной
  cost (без них ~15fps в software). Не является дефектом кода; см. performance-док.
- **Console AbortError при unmount карты** во время загрузки стиля — известный артефакт
  cleanup MapLibre (`map.remove()` → abort fetch). Отфильтрован в e2e-харнессе
  (`AbortError: signal is aborted`), не влияет на функциональность.
- **Высоты зданий** могут быть оценкой по `building:levels` (OSM), не точный обмер —
  зафиксировано в data-contract и легенде.
- **In-range swap координат** (Москва) эвристикой не ловится — документированный
  blind spot GEO-4 backend; frontend не угадывает.
- Скриншоты сняты реальным браузером; модель-агент не имеет vision-входа, поэтому
  визуальная проверка выполнялась программно (DOM/WebGL introspection, feature counts,
  console errors) + скриншоты приложены как артефакты для человеческого ревью.

## 8. Скриншоты (docs/assets/geospatial/)

`2d-map.png`, `3d-city.png`, `3d-selected-asset.png`, `infrastructure-view.png`,
`selected-observation.png`, `selected-defect.png`, `hexbin-2d.png`, `hexbin-defects.png`,
`walkthrough-compare.png`, `mobile-390-map.png`.
