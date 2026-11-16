# REVIZOR Frontend

Public Showcase (`/`) + Command Center (`/app`) для платформы мониторинга
телеком-инфраструктуры. Backend не изменяется; источник истины по данным —
`contracts/openapi/openapi.json` и `docs/integrations/frontend-contract.md`.

## Стек

React 18 · TypeScript · Vite 6 · TanStack Query v5 · react-router v6 ·
MapLibre GL JS (lazy) · GSAP + ScrollTrigger (lazy) · openapi-fetch +
сгенерированный `schema.d.ts` · собственные SVG-графики · plain CSS + design tokens.

Обоснование выбора: frontend в репозитории отсутствовал; repo готовит
typed-контракт (openapi-typescript/openapi-fetch), 10 рабочих разделов с
мутациями и polling требуют компонентной модели и code splitting.
Шрифты (Oswald / IBM Plex Sans / JetBrains Mono, OFL) и фото (CC BY / CC0,
Wikimedia Commons) хранятся локально — `public/assets/SOURCES.md`.

## Команды

```bash
cd frontend
npm install
npm run dev          # dev-сервер :5173, proxy /api,/health,/docs → :8000
npm run build        # tsc + production build → dist/
npm run preview      # production preview :4173 (proxy на :8000)
npm run lint         # typecheck (tsc --noEmit)
npm test             # vitest unit (28 тестов)
npm run test:e2e     # Playwright: showcase + demo + responsive + robustness
npm run test:e2e:live  # Playwright @live: против реального backend (:8000)
node scripts/visual-qa.mjs   # программный визуальный QA + скриншоты
node scripts/perf.mjs        # LCP/CLS/long tasks (PERF_BASE для preview)
```

Backend для live-режима: `make dev` из корня (или `make up`), затем `make seed`.
Демо-доступ: `demo-operator / demo-operator-password` (dev).

## Архитектура

```
src/
├── api/          schema.d.ts (из contracts/typescript), client.ts (openapi-fetch,
│                 auth-middleware, ApiError, unwrap), auth.tsx, uploads.ts (XHR progress)
├── data/         source.tsx (live|demo контекст), hooks.ts (TanStack Query hooks,
│                 ключи включают mode → кэш live/demo не смешивается)
├── demo/         data.ts (детерминированный синтетический датасет), provider.ts
│                 (те же формы ответов + мутации + симуляция job), frames.ts (SVG-кадры)
├── components/   ui.tsx, icons.tsx, charts.tsx, map/ (NetworkMap→MapView|SchematicMap)
├── showcase/     ShowcasePage + 7 сцен, NetworkSvg, motion.ts, useShowcaseData.ts
├── app/          AppShell + 15 страниц (Overview…Exports, паспорта, детали)
├── lib/          labels.ts (RU-справочники), format.ts, bbox.ts, permissions.ts
├── styles/       tokens / base / components / app / showcase
└── tests/        vitest unit
e2e/              showcase / app-demo / app-live (@live) / responsive / robustness
```

### Режимы данных

- **live**: JWT-сессия (`localStorage`, expiry), все запросы через openapi-fetch
  к реальному API. 401 → очистка сессии → `/login`. Роли: VIEWER — только чтение.
- **demo**: явное включение (кнопка на `/login`, переключатель в rail).
  Детерминированный синтетический датасет, маркировка DEMO на каждом экране,
  мутации применяются к demo-хранилищу, job-обработка симулируется таймером.
  Кэш TanStack Query разделён ключами `[resource, mode, params]`.
- **showcase**: при наличии сессии — данные API; иначе.demo-сценарий с явной
  маркировкой «ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ».

### Карта

MapLibre GL: тёмный raster basemap (Esri World Dark Gray, без API-ключа, attribution), GeoJSON-слои
assets (кластеризация) / defects (кольца) / observations / routes, selection,
popup, fitBounds. Fallback при отказе WebGL или >8 ошибках тайлов →
интерактивная SVG-схема с координатной сеткой (без выдуманной географии),
pan/zoom, keyboard-доступные точки. Карта монтируется только рядом с viewport.

## API integration map

| Раздел | Endpoints |
|---|---|
| Auth | POST /auth/login, POST /auth/logout, GET /auth/me (через login-response) |
| Overview | GET /analytics/overview, /assets?priority_band=HIGH_PRIORITY, /defects?severity_min=4, /observations, /jobs, /map/assets, /map/routes |
| Map | GET /map/assets, /map/defects, /map/observations, /map/routes |
| Assets | GET /assets (фильтры/сортировка/пагинация), GET/PATCH /assets/{id}, /assets/{id}/history, /observations, /defects |
| Observations | GET /observations (review_status, dedup_result, object_type, asset_id, job_id), GET /observations/{id} |
| Defects | GET /defects (status, defect_type, severity_min), GET/PATCH /defects/{id} |
| Reviews | GET /observations?review_status=UNREVIEWED, POST /reviews (Idempotency-Key), GET /reviews?observation_id |
| Jobs | POST /uploads (multipart, XHR progress), POST /jobs, GET /jobs (polling 2s), GET /jobs/{id} (polling 1.5s), /jobs/{id}/frames, POST /jobs/{id}/retry, /cancel |
| Routes | GET /routes, GET /routes/{id}, POST /routes |
| Analytics | GET /analytics/overview, /analytics/defects, /analytics/coverage + клиентская группировка observed_at (методология подписана) |
| Exports | GET /exports/{assets,defects,observations}?format=csv|xlsx (blob + auth) |
| ML status | GET /ml/health, /ml/model-info (hook useMlStatus) |

## Известные ограничения / gaps backend

1. **Нет time-series endpoint** — динамика наблюдений строится клиентской
   группировкой последних ≤300 записей (методология указана в UI).
2. **Нет списка наблюдений конкретного дефекта** — в карточке дефекта
   показываются наблюдения объекта + observation_count (подписано).
3. **Нет user-management API** — VIEWER-роль проверяется логикой canMutate,
   но создать viewer-пользователя через API нельзя (bootstrap admin + seed).
4. **GPS-трек загрузки** — контракт поддерживает metadata.gps_track; UI передаёт
   route_id, ввод GPS-трека в форме загрузки не реализован (трек задаётся
   через Routes). Без GPS объекты создаются UNAVAILABLE — координаты не выдумываются.
5. **Presigned URL** живут ограниченное время — при истечении UI показывает
   «Кадр недоступен» с метаданными (не подставляет заглушку).
6. **Анонимизация** в MVP не применяется (NoopPrivacyFilter → NOT_APPLIED);
   UI честно подписывает, что кадр показан как есть.

## Тесты и QA

- unit: 28 (детерминизм demo, фильтры/пагинация, review-логика, оптимистичная
  блокировка, форматтеры, bbox, семантика статусов).
- E2E: showcase (6), demo (10), live @live (7), responsive (10), robustness (9).
- Программный визуальный QA: контрасты токенов, типографика, композиция hero,
  scrub-прогресс, WebGL/attribution, focus states, перекрытия на мобильных.
- Performance (production preview): LCP 296–1124ms, CLS ≤0.023.
- Скриншоты: `artifacts/qa/` (не коммитятся).

## Принципы (anti-slop)

См. `docs/design/DIRECTION.md`, `docs/design-system.md`,
`docs/design/ANTI-SLOP-AUDIT.md`. Коротко: предметная специфика вместо
шаблонного SaaS; статус = цвет+текст+форма; demo маркирован; отсутствие
данных — «—», не ноль; никаких фейковых прогрессов и выдуманных координат.