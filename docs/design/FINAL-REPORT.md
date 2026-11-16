# REVIZOR — финальный отчёт (Showcase + Command Center)

Дата: 16 ноября 2026. Все результаты подтверждены фактическим запуском
(dev :5173, production preview :4173, backend :8000 в Docker, seed-данные).

## 1. Исходное состояние

Frontend в репозитории **отсутствовал** — только backend (FastAPI, 47 endpoints,
OpenAPI 3.1, 661 тест, seed). Frontend создан с нуля в `frontend/`; backend и
API-контракты **не изменялись** (`git status`: только новые `frontend/`, `docs/`).

## 2. Визуальная концепция

**THE CITY IS A NETWORK.** Три мира: urban photography (реальная аэросъёмка
Москвы, CC BY 4.0 / CC0, локально), geospatial intelligence (сеть, координаты,
слои), infrastructure operations (диспетчерская, статусы, история).
Палитра: deep graphite `#091318` / mint `#75D7CC` / amber `#F0A45C` /
red `#E66C61` + редакционная светлая сцена `#F2F3EF`. Типографика:
**Oswald** (display) / **IBM Plex Sans** (интерфейс) / **JetBrains Mono**
(данные) — локально, OFL, кириллица. Контрасты всех токенов проверены расчётом
(текст ≥5.5:1, границы контролов 3.13:1).

## 3. Адаптированные решения KDF (без копирования контента)

Две самостоятельные части `/` и `/app` с прямыми URL; scroll-scrub без
scroll-jacking (sticky-трек, обратим, rAF только при изменении); единая
система движения (180/240/550ms, power3.out); раздельные границы контролов и
декоративные линии; радиусы 3–7px; честность данных (DEMO-маркировка, «—»
вместо нуля, единицы меньше значений); интерактивный SVG-fallback при отказе
WebGL; остановка тяжёлых сцен вне viewport; QA-дисциплина (Playwright-evidence,
два визуальных цикла, расчёт контрастов, ширины 360–1920).

## 4. Созданные страницы

- **Showcase `/`**: Hero (ночная аэросъёмка + прорисовка сети + координатная
  строка) → Invisible Network (scrub фото→схема, счётчики) → Pipeline (светлая
  редакционная сцена, 8 стадий с SVG-иллюстрациями) → Digital Infrastructure
  (интерактивная карта, слои, паспорт по клику) → Intelligence in Action
  (6-шаговый сценарий с интерактивным решением) → Command Center preview
  (живые компоненты) → Final CTA → футер с атрибуцией.
- **Command Center `/app`**: Overview, Map, Assets (+паспорт), Observations
  (+деталь), Defects (+деталь), Reviews, Jobs (+деталь), Routes (+деталь),
  Analytics, Exports, Login. 15 страниц, единый shell, адаптив.

## 5. Компоненты и библиотеки

React 18 + TS + Vite 6; TanStack Query v5 (кэш, polling, invalidation);
react-router v6 (lazy routes); MapLibre GL (lazy chunk 218KB gz); GSAP +
ScrollTrigger (lazy chunk 46KB gz); openapi-fetch + `schema.d.ts` из
`contracts/typescript`; собственные SVG-графики (HBar/Column/Sparkline/
Stacked/CoverageGrid/TimeHistogram); собственный SVG-набор иконок; plain CSS
+ design tokens. Entry 10KB gz, vendor 66KB gz; страницы 2–4.5KB gz.

## 6. Подключённые API (live-режим проверен E2E)

auth/login+logout; analytics/overview+defects+coverage; assets (фильтры,
сортировка whitelist, пагинация, PATCH с expected_version, history,
observations, defects); observations (все фильтры контракта); defects
(PATCH status/severity); reviews (POST с Idempotency-Key, append-only
история); uploads (multipart XHR-progress) + jobs (polling 1.5–2s, frames,
retry/cancel); routes (GET/POST с треком); map/* GeoJSON; exports CSV/XLSX
(blob + auth); ml/health+model-info (hook).

## 7. Что действительно работает (подтверждено тестами)

- Live: вход demo-operator → реальные агрегаты (18 assets / 33 observations /
  16 defects); реальное CONFIRMED-review через API с уменьшением очереди;
  реальная загрузка JPEG → job → терминальный статус; GeoJSON-слои; экспорт.
- Demo: полный цикл без сервера (очередь→решение→история, upload→симуляция
  job→новые наблюдения, создание маршрута, смена статуса дефекта, CSV).
- Fallback: отказ WebGL → интерактивная SVG-схема с выбором; отказ тайлов →
  схема; ошибка API → ErrorState с request_id и retry; пустой фильтр →
  EmptyState; конфликт версий 409 → сообщение оператору.
- A11y: skip-link, focus-visible, клавиша Enter на строках, клавиши 1–4 в
  Reviews, нативные dialog с Escape, aria-sort/aria-live/role.
- Reduced motion: статичный рассказ, все функции доступны (E2E).
- Responsive: 0 горизонтальных переполнений на 360/375/390/768/1024/1280/1440/1920.
- Performance (production): LCP 296–1124ms, CLS ≤0.023, long tasks ≤389ms.

## 8. Ограничения backend (зафиксированы, не изобретались)

Нет time-series endpoint (динамика — клиентская группировка ≤300 записей,
методология подписана); нет списка наблюдений дефекта (показаны наблюдения
объекта + observation_count); нет user-management API (VIEWER проверяется
логикой, но не создаётся через API); GPS-трек в форме загрузки не реализован
(задаётся через Routes/metadata контракта); presigned URL истекают → честное
«Кадр недоступен»; анонимизация NOT_APPLIED → кадр показан как есть с подписью.

## 9. Тесты

- **Unit (vitest): 28 passed** — детерминизм demo, фильтры/пагинация,
  review-логика (CONFIRMED/CORRECTED/422), оптимистичная блокировка,
  форматтеры, bbox, семантика статусов.
- **E2E (Playwright): 42 passed** — showcase 6, demo 10, live 7,
  responsive 10, robustness 9. 0 ошибок JS в консоли во всех сценариях.
- Программный визуальный QA: контрасты, типографика (шрифты загружены),
  композиция hero без перекрытий, scrub-прогресс (15/15 путей, opacity 1→0),
  WebGL-canvas + attribution, focus-outline.

## 10. Оставшиеся проблемы

- Визуальная проверка выполнена программно (модель не поддерживает просмотр
  изображений); скриншоты приложены для человеческого ревью — возможна
  субъективная доводка вкусовых деталей.
- MapLibre chunk 218KB gz — неустранимо для WebGL-карты; загружается лениво.
- Один long task ~389ms при инициализации карты в showcase (при прокрутке к сцене).
- Демо-данные job-обработки симулируются таймером (явно маркировано DEMO).

## 11. Screenshots

`frontend/artifacts/qa/` (60 файлов): `01-hero`, `02-network-mid`,
`03-pipeline`, `04-twin-map`, `05-scenario`, `06-platform-preview`,
`07-final-cta` (showcase); `10-app-overview`, `11-app-map`, `13-app-passport`,
`14-app-reviews`, `16-app-analytics` (demo); `20-live-overview`, `22-live-map`,
`23-live-reviews`, `24-live-job` (live); `30-svg-fallback`, `32-error-state`,
`33-empty-state`, `34-conflict` (состояния); `mobile-390-*`, `qa1-*-390`,
`qa2-net-fixed-*` (мобильные); `qa1-*` (цикл 1), `qa2-*` (цикл 2).
Отчёты: `visual-qa-cycle1.json`, `performance.json`, `results.json`.

## 12. Команды запуска

```bash
# backend (из корня)
make dev && make seed          # :8000, demo-operator / demo-operator-password
# frontend
cd frontend && npm install
npm run dev                    # :5173 (proxy на :8000)
npm run build && npm run preview  # production :4173
npm test                       # unit
npm run test:e2e               # E2E demo/showcase/responsive/robustness
npm run test:e2e:live          # E2E против живого API
```