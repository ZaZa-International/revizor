# REVIZOR — Visual / UX / Frontend Audit (Phase 0)

Дата: 17 ноября 2026. Область: весь frontend (`frontend/`), Public Showcase `/`
и Command Center `/app`. Backend и API-контракты не изменяются.

## 0. Метод и ограничения

- Полный обход кода: 17 маршрутов, ~12 500 строк TSX/TS/CSS, все ассеты.
- Программный визуальный QA в реальном браузере (Playwright):
  `scripts/visual-audit.mjs` → `frontend/artifacts/audit-before/report.json`
  + скриншоты всех страниц на 1440 и 390.
- **Ограничение среды: модель не поддерживает просмотр изображений.**
  Визуальные выводы получены из DOM-метрик (геометрия, контраст реального
  текста, масштабы SVG, переполнения) и анализа кода, а не из просмотра
  пикселей. Скриншоты приложены для человеческого ревью. Субъективные
  оценки арт-дирекции в отчётах помечены как код-анализ.
- Предыдущий проход дизайна зафиксирован в `docs/design/` (DIRECTION,
  ANTI-SLOP-AUDIT, FINAL-REPORT). Настоящий аудит — независимая повторная
  проверка с исправлением найденного.

## 1. Карта страниц

| Маршрут | Компонент | Задача | Состояния |
|---|---|---|---|
| `/` | showcase/ShowcasePage | презентация продукта: Hero → InvisibleNetwork (scrub) → Pipeline → DigitalTwin → Scenario → PlatformPreview → FinalCta | live/demo, reduced-motion |
| `/login` | app/LoginPage | вход + демо-режим | error inline, health |
| `/app` | app/OverviewPage | сводка: 4 KPI, внимание, карта, очередь, jobs | loading/error/empty по панелям (jobs — без error) |
| `/app/map` | app/MapPage | главный инструмент: 7 слоёв, 2D/3D, фильтры, легенда, инспекция | URL-состояние, fallback SVG, perf-панель |
| `/app/assets` | app/AssetsPage | реестр: поиск, 4 фильтра, сортировка, таблица + mobile-карточки | loading/error/empty |
| `/app/assets/:id` | app/AssetPassportPage | паспорт: KeyValue, факторы приоритета, мини-карта, вкладки observations/defects/history, edit-диалог | optimistic lock 409 |
| `/app/observations` | app/ObservationsPage | материалы обследования: кропы 76×46, фильтры | loading/error/empty |
| `/app/observations/:id` | app/ObservationDetailPage | кадр + bbox overlay, ML vs effective, dedup JSON, история review | «кадр недоступен» |
| `/app/defects` | app/DefectsPage | реестр дефектов, severity desc | loading/error/empty |
| `/app/defects/:id` | app/DefectDetailPage | карточка + edit-панель (role-gated) | read-only для VIEWER |
| `/app/reviews` | app/ReviewsPage | рабочее место оператора: очередь ≤50, кадр+bbox, 4 решения, клавиши 1–4 | auto-advance, idempotency |
| `/app/jobs` | app/JobsPage | загрузка (drag-drop, XHR progress) + монитор jobs | polling 2s |
| `/app/jobs/:id` | app/JobDetailPage | pipeline monitor: stage-track 13 стадий, кадры, retry/cancel | polling 1.5s |
| `/app/routes` | app/RoutesPage | маршруты + создание (JSON-трек) | валидация координат |
| `/app/routes/:id` | app/RouteDetailPage | трек на карте, jobs | упрощение: observations только первого job |
| `/app/analytics` | app/AnalyticsPage | 7 панелей: распределения, severity, статусы, время, покрытие | методология подписана |
| `/app/exports` | app/ExportsPage | CSV/XLSX выгрузки с фильтрами | ошибки только toast |
| `*` | NotFound (main.tsx) | 404 | — |

Глобально: ErrorBoundary, Suspense LoadingState, ToastStack (main.tsx),
skip-link, demo/live переключатель, RBAC через `canMutate`.

## 2. Карта компонентов

- **UI kit** (`components/ui.tsx`, 411 строк): Button, Status, Badge, Severity
  (бар-метр S1–S5), Field, SearchInput, LoadingState, EmptyState, ErrorState
  (request_id + retry), QueryState (**не используется**), Pagination, Dialog
  (нативный `<dialog>`), toast/ToastStack, Tabs, KeyValue, Progress, Legend,
  DemoBanner. Нет: Drawer, Tooltip-компонента (только native title), Skeleton,
  ConfirmDialog, Dropdown.
- **Charts** (`components/charts.tsx`): HBarList (HTML), ColumnChart (SVG,
  **дефект масштаба**), Sparkline (**не используется**), StackedBar (HTML),
  CoverageGrid (SVG), TimeHistogram (обёртка ColumnChart).
- **Map**: NetworkMap (lazy + WebGL-probe) → MapView (MapLibre, 9 слоёв,
  кластеры, fallback-цепочка vector→raster→SVG) | SchematicMap (интерактивный
  SVG-fallback), DeckOverlay (hexbin, lazy), inspection.tsx (4 панели +
  HistoryTimeline + ObservationCompare).
- **Showcase**: 7 сцен, NetworkSvg (декоративная схема, scrub draw-on),
  motion.ts (reveal + near-viewport + reduced-motion), useShowcaseData.
- **Demo**: data.ts (детерминированный датасет), provider.ts (те же формы
  ответов + мутации), frames.ts (**синтетические SVG-«кадры»**), walkthrough.

## 3. Реестр визуальных ассетов

### Изображения (public/assets/img, локально, лицензии проверены)
| Файл | Байт | Использование | Лицензия |
|---|---|---|---|
| hero-night-768/1280/1920/2560.webp | 17k/36k/70k/182k | Hero srcSet | CC BY 4.0, Vyacheslav Argenberg (Wikimedia) |
| hero-night-lqip.webp | 132 | Hero background-placeholder | CC BY 4.0 |
| aerial-day-768/1280/1920.webp | 39k/89k/242k | InvisibleNetwork srcSet | CC BY 4.0 |
| aerial-day-lqip.webp | 142 | **не используется** | CC BY 4.0 |
| skyline-1280/1920.webp | 193k/386k | FinalCta srcSet | CC0, Александр Сигачёв |
| skyline-lqip.webp | 182 | **не используется** | CC0 |

Атрибуция: SOURCES.md + футер ShowcasePage.tsx:74-89. Реальных кадров
обследования в репозитории нет: seed backend и e2e-фикстуры синтетические;
demo-кадры рисуются в frames.ts и честно маркированы «DEMO · СИНТЕТИЧЕСКИЙ КАДР».

### Шрифты (OFL 1.1, локально, 44 woff2)
- Oswald 400/500/600/700 — используются только 500/600; **400 и 700 мертвы** (8 файлов).
- IBM Plex Sans 400/500/600/700 — все используются.
- JetBrains Mono 400/500/700 — **600 запрашивается в CSS (app.css:529, 824, 857), но face не объявлен** → подмена/синтез.
- Preload: oswald-cyrillic-600, plex-cyrillic-400; mono не предзагружается.

### SVG
- favicon.svg — брендовый знак (сеть-треугольник), используется в 4 местах. OK.
- icons.tsx — 32 иконки + assetTypeIcon (см. §4).
- charts.tsx — функциональные графики (ColumnChart дефектен).
- SchematicMap.tsx — функциональный fallback карты.
- NetworkSvg.tsx — декоративная схема сети, явно «не географическая карта». OK по смыслу, цвета захардкожены.
- LoginPage.tsx:9-29 — декоративная «сеть» на фоне. OK по смыслу, цвета захардкожены.
- **Pipeline.tsx:15-126 — 8 декоративных SVG-«картинок» с выдуманными значениями** (главная проблема).
- **Scenario.tsx:13-52 — 2 SVG с захардкоженными данными вместо HTML**.
- frames.ts — синтетические кадры (ночной город-«мультфильм»).
- components.css:273 — data-URI шеврон select (функциональный).

### Видео
Видеофайлов в репозитории нет; загрузка видео — реальный flow через API.

## 4. Реестр иконок (icons.tsx)

Единая сетка 24×24, stroke 1.6 (CSS components.css:776-785), currentColor,
aria-hidden по умолчанию, icon-only кнопки с aria-label. Стиль согласован.

- **Навигация (10)**: Overview, Map, Asset, Observation, Defect, Review, Job,
  Route, Analytics, Export — используются в rail.
- **Действия/состояния (12)**: Search, Plus, Close, Check, Alert, ChevronDown,
  ChevronLeft, ChevronRight, ArrowRight, Upload, External, Logout.
- **Доменные (4)**: Well, Pole, Cabinet, Cable — через assetTypeIcon, единый
  стиль, силуэты читаемы. Fallback IconAsset.
- **Мертвые (6)**: Clock, Target, Layers, Filter, Refresh, Menu — удалить.
- Артефакт: `strokeDasharray="0"` на IconRoute (icons.tsx:63).
- Оптические выбросы: eye/target выходят за 3–21 в 2–22 (некритично).

Сторонних icon-библиотек нет; смешения стилей нет. glyphs `+ − ⌂` в
SchematicMap и `↓ ↑` в сортировке — текстовые, не иконки (унифицировать).

## 5. Повторяющиеся визуальные паттерны

1. `panel` + `panel-title` + таблица/список — все реестры. Оправдано.
2. `kpi-strip` (Overview) и `factor-grid` (Passport, JobDetail) — стат-блоки
   без иконок и декора. Оправдано.
3. `overview-grid` / `detail-grid` / `analytics-grid` — сетки панелей. Оправдано.
4. `attention-item` — строки «объект + статус + число». Оправдано.
5. Status/Badge/Severity — единая семантика через lib/labels.ts. Оправдано.
6. `eyebrow` (mono uppercase) над заголовком — везде. Оправдано, идентичность.
7. Showcase: `sc-section-head` + сцена — редакционный ритм. Оправдано.
8. **Pipeline: 8 одинаковых строк «номер + текст + SVG-картинка»** — шаблонная
   композиция с декоративным содержимым. Переработать.
9. `preview-card` с `.dots` (фейковое оконное обрамление) — декор без смысла. Удалить.

## 6. Проблемы (severity: P1 — существенно вредит продукту, P2 — заметно, P3 — гигиена)

| ID | Sev | Проблема | Файл:строки | Исправление | Трудоёмкость |
|---|---|---|---|---|---|
| VA-01 | P1 | ColumnChart: `preserveAspectRatio="none"` растягивает текст ×5.28 по X; подписи осей рендерятся ~6px высотой — нечитаемы | charts.tsx:69-92 | переписать на HTML/CSS-колонки с настоящими осями и подписями | M |
| VA-02 | P1 | ColumnChart без empty-ветки (нулевые бары вместо «нет данных») | charts.tsx:49-104 | empty-ветка как у HBarList | S |
| VA-03 | P1 | Pipeline showcase: 8 условных SVG-картинок с выдуманными значениями («telecom_well 0.92», «priority 87/100», даты) вместо реальных материалов продукта | Pipeline.tsx:15-126 | заменить визуалами из demo-данных и реальных UI-компонентов (кадр+bbox, quality-метрики, dedup-координаты, факторы, review, timeline) | L |
| VA-04 | P1 | Scenario: DedupVisual/HistoryVisual — захардкоженные значения в SVG-text, generic monospace | Scenario.tsx:13-52 | HTML-визуалы, значения из demoData | M |
| VA-05 | P2 | Fallback-статистика showcase 18/34/12 не совпадает с demo-датасетом (16/28/9) — ложные числа до загрузки | ShowcasePage.tsx:24-29 | брать из demoProvider/датасета, «—» до загрузки | S |
| VA-06 | P1 | Баг: `useMapRoutes({ enabled: live })` — enabled уходит в query-параметры API, запрос всегда включён → 401 в консоли без сессии | useShowcaseData.ts:15, DigitalTwin.tsx:27 | `useMapRoutes({}, { enabled: live })` | S |
| VA-07 | P2 | Контраст активной кнопки 2D/3D = 3.47 (<4.5): ink на accent-dim | app.css:534-537 | .on = accent + accent-ink (как primary button) | S |
| VA-08 | P2 | Сортировка таблицы только мышью: th onClick без button/tabindex | AssetsPage.tsx:54-63 | button внутри th, aria-sort сохраняется | S |
| VA-09 | P2 | Tabs: нет arrow-key навигации, roving tabindex, связи tabpanel | ui.tsx:327-352 | WAI-ARIA tabs pattern | S |
| VA-10 | P2 | Toast: нет закрытия, нет pause при hover; ошибка исчезает через 5.2s | ui.tsx:303-324 | close-кнопка + hover-pause | S |
| VA-11 | P2 | Отмена job без подтверждения (деструктивное действие) | JobDetailPage.tsx:64 | ConfirmDialog | S |
| VA-12 | P2 | Upload заявляет «до 2 ГБ», но клиентского size-check нет | JobsPage.tsx:130 | проверка MAX_UPLOAD_SIZE_BYTES (2147483648) до XHR | S |
| VA-13 | P2 | Overview: jobs-панель без ErrorState | OverviewPage.tsx:217-244 | добавить ветку error | S |
| VA-14 | P3 | 6 мертвых иконок + strokeDasharray="0" | icons.tsx:147-184, 63 | удалить | S |
| VA-15 | P3 | Sparkline экспортирован, не используется | charts.tsx:107-129 | удалить | S |
| VA-16 | P3 | JetBrains Mono 600 запрашивается, face не существует | app.css:529, 824, 857 | заменить на 500/700 | S |
| VA-17 | P3 | Oswald 400/700 объявлены, не используются (8 woff2) | fonts.css, public/assets/fonts | удалить face+файлы | S |
| VA-18 | P3 | LQIP aerial-day/skyline не подключены (hero использует) | InvisibleNetwork.tsx:50-56, FinalCta.tsx:22-26 | подключить как background-placeholder | S |
| VA-19 | P3 | Дублирование цветов токенов литералами в inline SVG | NetworkSvg.tsx:60,96,110; SchematicMap.tsx:150,172,194,224; charts.tsx:188; LoginPage.tsx:22,25; Scenario.tsx:10-11 | CSS-переменные в inline SVG | M |
| VA-20 | P3 | generic `monospace` вместо JetBrains Mono в SVG-подписях | frames.ts:72,86-87; Pipeline; Scenario | JBM там, где достижим (data-URL SVG — ограничение формата, задокументировать) | S |
| VA-21 | P2 | Dialog: нет начального фокуса на первом поле | ui.tsx:241-285 | autoFocus первого focusable при открытии | S |
| VA-22 | P3 | Строки подтаблиц паспорта не клавиатурные | AssetPassportPage.tsx:169-288 | tabIndex+Enter по образцу реестров | S |
| VA-23 | P3 | Hover-popup карты только для assets; defects/observations без обратной связи | MapView.tsx:524-531 | popup для всех interactive слоёв | M |
| VA-24 | P3 | Zoom-кнопки SchematicMap — текстовые glyphs | SchematicMap.tsx:235-237 | иконки Plus/Close/Target или унифицированные glyphs | S |
| VA-25 | P3 | Exports: ошибки только toast, нет inline-состояния | ExportsPage.tsx:127 | inline error в карточке | S |
| VA-26 | P3 | QueryState определён, не используется (дублирование веток состояний) | ui.tsx:188-201 | удалить либо внедрить точечно | S |
| VA-27 | P2 | Demo-кадры — «мультяшный» ночной город; слабо передают предметную область (дневной объезд, уличная инфраструктура) | frames.ts:43-90 | перерисовать: дневная уличная сцена, объект у дороги, честная DEMO-маркировка сохраняется | M |
| VA-28 | P3 | `.preview-card .dots` — фейковое оконное обрамление, не несёт смысла | PlatformPreview.tsx:37,79,107; showcase.css:620-630 | удалить | S |
| VA-29 | P3 | mono не предзагружается, хотя это шрифт данных | index.html:12-13 | preload jetbrains-mono-cyrillic-500 | S |
| VA-30 | P2 | Mobile: таблицы Observations/Defects/Jobs/Routes только горизонтальный скролл (7 колонок с кропами) | app.css:1319+ | задокументировано как enterprise-паттерн; sticky-первая колонка — опционально | M |
| VA-31 | P3 | Карта: кольца дефектов поверх точек assets в тех же координатах; длинная легенда | MapView.tsx:375-511; MapPage.tsx:276-302 | смещение колец/легенда компактнее — низкий приоритет | M |
| VA-32 | P3 | bbox-label chip в frames.ts: ширина по эвристике `len*9+130` может не совпасть с текстом | frames.ts:71 | считать по фактической длине строки | S |

## 7. Что уже хорошо (сохранить)

- Тёмная графитовая система без glow/градиентов/glass на рабочих поверхностях;
  единственный shadow-токен для оверлеев; плоские KPI без иконок.
- Типографика Oswald/Plex/JBM с кириллицей, локально, OFL; контрасты токенов
  ≥4.5 (проверено расчётом и DOM-аудитом: 0 нарушений на страницах app).
- Честность данных: DEMO-маркировка везде, «—» вместо нуля, методология
  графиков подписана, NOT_APPLIED privacy показан, GPS UNAVAILABLE не выдумывается.
- Единая семантика статусов (lib/labels.ts), Severity-метр, append-only история.
- Карта: реальная векторная базовая карта, кластеры, 2D/3D, трёхступенчатый
  fallback, URL-состояние, лимиты 2000/слой.
- A11y-каркас: skip-link, focus-visible, native dialog, aria-sort/aria-live,
  клавиши 1–4 в Reviews, reduced-motion.
- 0 горизонтальных переполнений документа на 360–1920 (подтверждено аудитом).
- Редакционная композиция showcase (разные типы сцен, не карточки).

## 8. Приоритет работ

1. VA-01/02 (графики), VA-06 (баг 401), VA-05 (ложные числа) — быстрые, критичные.
2. VA-03/04/27 (демонстрация CV и pipeline) — ядро бренда, Largest effort.
3. VA-07–13, VA-21 (a11y и рабочие состояния) — S-правки, высокий эффект.
4. VA-14–20, VA-24–29, VA-32 (гигиена ассетов/токенов).
5. VA-23, VA-30, VA-31 — по остаточному принципу, документируются.

Baseline-артефакты: `frontend/artifacts/audit-before/` (скриншоты всех страниц
1440/390 + report.json). Повторный прогон после изменений: `audit-after`.