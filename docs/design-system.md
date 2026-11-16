# REVIZOR Design System

Единая система для Public Showcase (`/`) и Command Center (`/app`).
Токены: `frontend/src/styles/tokens.css`. База: `base.css`. Компоненты:
`components.css`. Рабочая среда: `app.css`. Презентация: `showcase.css`.

## 1. Цветовые токены

Контрасты проверены расчётом (WCAG 2.1 relative luminance; скрипт
`frontend/scripts/visual-qa.mjs`, отчёт `artifacts/qa/visual-qa-cycle1.json`).

### Тёмная рабочая среда

| Токен | Значение | Назначение | Контраст |
|---|---|---|---|
| `--bg` | `#091318` | основная поверхность | — |
| `--surface` | `#102129` | панели, rail | — |
| `--raised` | `#1C3038` | вторичные поверхности, hover | — |
| `--overlay` | `#0C1A21` | диалоги, тосты | — |
| `--line` | `#24404A` | декоративные разделители | — |
| `--line-soft` | `#1A313A` | мягкие разделители | — |
| `--control-border` | `#55707A` | границы полей/кнопок | 3.13:1 к surface (≥3) |
| `--ink` | `#E9EEE9` | основной текст | 15.99:1 к bg |
| `--muted` | `#A0B3B5` | вторичный текст | 7.56:1 к surface |
| `--faint` | `#7D959B` | третичный текст | 5.94:1 к bg |
| `--accent` | `#75D7CC` | сеть, действия, выделение | 11.05:1 к bg |
| `--accent-ink` | `#06231F` | текст на accent | 9.74:1 |
| `--ok` | `#9DBFA8` | исправен / завершено | 9.35:1 |
| `--warn` | `#F0A45C` | предупреждение / ожидает | 9.10:1 |
| `--crit` | `#E66C61` | критический дефект | 5.98:1 |

### Редакционная светлая сцена (pipeline)

| Токен | Значение | Контраст |
|---|---|---|
| `--paper` | `#F2F3EF` | — |
| `--paper-ink` | `#14232B` | 14.44:1 |
| `--paper-muted` | `#4E6268` | 5.76:1 |
| `--paper-accent` | `#0E6E62` | 5.50:1 |
| `--paper-line` | `#D3D8CF` | — |

Правила семантики:
- Статус = **цвет + текст + форма маркера** (круг/квадрат/ромб). никогда только цвет.
- Severity (S1–S5) — отдельная шкала с барами, не смешивается с priority band и confidence.
- Один акцент (`--accent`) для действий; семантические цвета только для состояний.
- DEMO-маркировка всегда `--warn` + текст «DEMO», никогда не смешивается с live.

## 2. Типографика

Локальные шрифты (OFL, кириллица): `public/assets/fonts/`, 44 woff2-файла
(subset cyrillic/cyrillic-ext/latin/latin-ext), `font-display: swap`.

| Роль | Шрифт | Начертания | Размеры |
|---|---|---|---|
| Display | **Oswald** | 500/600, uppercase, tracking 0.015–0.16em | hero `clamp(44px,7.2vw,108px)`; сцены `clamp(30px,4.4vw,58px)`; страницы 26px; панели 17px |
| Интерфейс/текст | **IBM Plex Sans** | 400/500/600 | body 15px/1.5; small 13px; micro 11px |
| Данные | **JetBrains Mono** | 400/500/700, `tabular-nums` | координаты, ID, счётчики, технические подписи |

Правила: числа табличные; единицы измерения меньше значения (`.unit`, 0.62em);
отсутствующие данные — «—», не ноль; координаты всегда `lat, lon` в UI-строке
и `[lon, lat]` в GeoJSON (контракт backend).

## 3. Ритм и формы

- Spacing: шаг 4px (`--sp-1…--sp-24`: 4/8/12/16/20/24/32/40/48/64/96).
- Радиусы: 3px контролы, 5px карточки/панели, 7px диалоги. Без «гигантских» скруглений.
- Тени: только временные слои (`--shadow-overlay`: диалоги, тосты). Панели разделяются линиями.
- Сетки: rail 232px; topbar 60px; контент ≤1480px; gutter 24px desktop / 16px mobile.
- Grid-колонки всегда `minmax(0, …)` + `min-width: 0` у детей (защита от min-content overflow).

## 4. Компоненты

`src/components/ui.tsx`: Button (default/primary/danger/ghost, sm/md/lg, loading),
Status (tone + shape), Badge (+demo), Severity (бары S1–S5), Field/SearchInput,
LoadingState/EmptyState/ErrorState/QueryState, Pagination, Dialog (нативный
`<dialog>`, Escape, возврат фокуса), ToastStack (aria-live), Tabs, KeyValue,
Progress, Legend, DemoBanner.

`src/components/charts.tsx`: HBarList, ColumnChart (ось Y, единицы), Sparkline,
StackedBar, CoverageGrid (heatmap), TimeHistogram. Все с aria-label и подписями
методологии. Без chart-библиотек.

`src/components/map/`: NetworkMap → MapView (MapLibre GL, lazy) → SchematicMap
(SVG fallback: координатная сетка, pan/zoom, keyboard-доступные точки).
Кластеризация assets, кольца дефектов, selection-ring, popup, attribution.

Иконки: `src/components/icons.tsx` — собственный SVG-набор (колодец, опора,
шкаф, кабель, карта, review, job, route…). Без emoji.

## 5. Движение

| Событие | Длительность | Easing |
|---|---|---|
| Micro (hover, press, цвет) | 180ms | `--ease-out` (0.22,1,0.36,1) |
| Смена карточки/шага | 240ms | opacity + transform |
| Вход/reveal | 550ms | translateY 20px → 0 |
| Scrub-сцена | scroll-driven | GSAP ScrollTrigger scrub 0.6, обратим |

- Нативная прокрутка, без scroll-jacking. Sticky-сцена «город → сеть» (260vh track).
- `prefers-reduced-motion`: все duration → 0, scrub отключён (статичный финал),
  reveal мгновенный, функции доступны без анимации.
- Тяжёлые сцены (карты) монтируются только рядом с viewport (`useNearViewport`,
  rootMargin 400–500px) и размонтируются при уходе (map.remove()).
- Параллакс hero — rAF только при scroll и только в пределах первого экрана.
- Никаких бесконечных декоративных циклов (единственное исключение —
  функциональный scroll-hint, отключается при reduced motion).

## 6. Состояния

Каждый data-экран: loading (spinner/skeleton) → error (код, message, request_id,
retry) → empty (объяснение + следующее действие) → data. Мутации: loading-кнопка,
success-тост, error с сохранением введённых значений. Оптимистичная блокировка
Asset: `expected_version`, 409 → понятное сообщение. Idempotency-Key на всех
POST uploads/jobs/reviews.

## 7. Доступность

- Skip-link, семантические landmarks, aria-label на картах/слоях/группах.
- `:focus-visible` outline 2px accent во всех интерактивных элементах.
- Нативные `<dialog>` (Escape, focus trap, возврат фокуса).
- Таблицы: сортировка с `aria-sort`, строки-ссылки с tabIndex + Enter.
- Контрасты ≥4.5:1 для текста, ≥3:1 для границ контролов (проверено расчётом).
- Статусы дублируются текстом; цвет не единственный носитель смысла.

## 8. Адаптивность

Проверенные ширины: 360/375/390/768/1024/1280/1440/1920 (E2E
`e2e/responsive.spec.ts`, 0 горизонтальных переполнений).
- ≤900px: rail → компактная верхняя навигация (10 разделов, внутренний
  горизонтальный скролл), карта первой на экране Map, панели ниже.
- ≤480px: KPI 2×2, attention-item wrap, фильтры на всю ширину.
- Таблицы — в `.table-wrap` с внутренним горизонтальным скроллом (страница не скроллится).