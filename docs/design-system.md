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

Локальные шрифты (OFL, кириллица): `public/assets/fonts/`, 36 woff2-файлов
(subset cyrillic/cyrillic-ext/latin/latin-ext), `font-display: swap`.
Неиспользуемые начертания удалены (Oswald 400/700); запрашивать только
существующие face (JetBrains Mono 600 не существует — использовать 500/700).

| Роль | Шрифт | Начертания | Размеры |
|---|---|---|---|
| Display | **Oswald** | 500/600, uppercase, tracking 0.015–0.16em | hero `clamp(44px,7.2vw,108px)`; сцены `clamp(30px,4.4vw,58px)`; страницы 26px; панели 17px |
| Интерфейс/текст | **IBM Plex Sans** | 400/500/600/700 | body 15px/1.5; small 13px; micro 11px |
| Данные | **JetBrains Mono** | 400/500/700, `tabular-nums` | координаты, ID, счётчики, технические подписи |

Preload: oswald-cyrillic-600, ibm-plex-sans-cyrillic-400, jetbrains-mono-cyrillic-500.
Моноширинный — только для данных/технических подписей, не для сплошного текста.
SVG-подписи внутри data-URL (demo-кадры) вынужденно используют generic monospace:
изолированный SVG не видит шрифты страницы и CSS-токены.

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
LoadingState/EmptyState/ErrorState, Pagination, Dialog (нативный `<dialog>`,
Escape, начальный фокус на первом поле/безопасной кнопке, возврат фокуса),
ToastStack (aria-live, close-кнопка, пауза таймера при hover/focus, error 10s),
Tabs (WAI-ARIA: roving tabindex, ArrowLeft/Right/Home/End, aria-controls →
tabpanel), KeyValue, Progress, Legend, DemoBanner. Деструктивные действия
(отмена job) — через confirm-диалог.

`src/components/charts.tsx`: HBarList (HTML), ColumnChart (HTML-колонки,
ось Y от нуля, подписи обычным текстом 11px, empty-ветки «Нет данных» /
«Нет данных за период»), StackedBar (HTML), CoverageGrid (SVG heatmap),
TimeHistogram (обёртка ColumnChart). Все с aria-label, единицами и подписями
методологии. Без chart-библиотек. Подписи данных НИКОГДА не масштабируются
вместе с графиком (запрет `preserveAspectRatio="none"` для текста).

`src/components/map/`: NetworkMap → MapView (MapLibre GL, lazy) → SchematicMap
(SVG fallback: координатная сетка, pan/zoom иконками, keyboard-доступные точки).
Кластеризация assets, кольца дефектов, selection-ring, hover-popup для всех
интерактивных слоёв (assets/defects/observations/routes), attribution.
Цвета карты — `geo/palette.ts` (документированное зеркало токенов: WebGL-paint
не принимает CSS-переменные).

Иконки: `src/components/icons.tsx` — единый SVG-набор 24×24/stroke 1.6,
currentColor, aria-hidden; доменные символы (колодец, опора, шкаф, кабель).
Правила и реестр — `docs/iconography.md`. Без emoji.

### Showcase: паттерн «specimen»

Стадии Pipeline и сценарий показывают реальные материалы продукта на
demo-данных: тёмная панель `.pipeline-specimen` на светлой редакционной сцене,
заголовок `источник (/app/…) + DEMO`. Внутри — настоящие компоненты (Status,
Severity, Progress, кадры с bbox, координаты, факторы, timeline). Запрещено:
выдуманные значения в SVG-иллюстрациях, одинаковые декоративные картинки
на каждый шаг, текст данных внутри SVG вместо HTML.

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
success-тост (dismissible), error с сохранением введённых значений. Оптимистичная
блокировка Asset: `expected_version`, 409 → понятное сообщение. Idempotency-Key
на всех POST uploads/jobs/reviews. Ошибки экспорта — inline в карточке (role=alert),
не только toast. Upload: клиентская проверка формата и размера (лимит backend
MAX_UPLOAD_SIZE_BYTES, сервер дополнительно 413). Отмена job — confirm-диалог.

## 7. Доступность

- Skip-link, семантические landmarks, aria-label на картах/слоях/группах.
- `:focus-visible` outline 2px accent во всех интерактивных элементах.
- Нативные `<dialog>` (Escape, focus trap, начальный фокус, возврат фокуса).
- Таблицы: сортировка — button внутри th с `aria-sort` (клавиатурная);
  строки-ссылки с tabIndex + Enter (включая подтаблицы паспорта).
- Tabs: roving tabindex + стрелки; tabpanel связан aria-controls/labelledby.
- Toast: close-кнопка (таргет 24px), пауза при hover/focus, aria-live.
- Контрасты ≥4.5:1 для текста, ≥3:1 для границ контролов (проверено расчётом
  и DOM-аудитом реального текста: `scripts/visual-audit.mjs`, 0 нарушений).
- Статусы дублируются текстом; цвет не единственный носитель смысла.
- Активные сегментированные переключатели: accent + accent-ink (9.7:1).

## 8. Адаптивность

Проверенные ширины: 360/375/390/768/1024/1280/1440/1920 (E2E
`e2e/responsive.spec.ts`, 0 горизонтальных переполнений).
- ≤900px: rail → компактная верхняя навигация (10 разделов, внутренний
  горизонтальный скролл), карта первой на экране Map, панели ниже.
- ≤480px: KPI 2×2, attention-item wrap, фильтры на всю ширину.
- Таблицы — в `.table-wrap` с внутренним горизонтальным скроллом (страница не скроллится).
- Assets на ≤768px: таблица → карточки; остальные реестры — скролл таблицы
  (осознанный enterprise-паттерн, документирован как остаток в visual-qa.md).
- Showcase specimens и scenario-dedup стекаются в одну колонку на ≤1024/768px.

## 9. Визуализация данных (единые правила)

Для каждого графика зафиксированы: вопрос пользователя, показатель, источник,
интерпретация, поведение при отсутствии данных.

| График | Вопрос | Показатель / источник | Empty |
|---|---|---|---|
| Overview · StackedBar | Сколько наблюдений проверено? | reviewed/total, analytics/overview | «Нет данных.» |
| Analytics · HBarList (типы) | Каких объектов больше? | assets_by_type, overview | «Нет данных для распределения.» |
| Analytics · HBarList (полосы) | Где сконцентрирован риск? | assets_by_priority_band + BAND_COLORS | то же |
| Analytics · ColumnChart (severity) | Насколько тяжёлые дефекты? | defects_by_severity, analytics/defects; ось Y от 0 | «Нет данных за период.» |
| Analytics · StackedBar (статусы) | Сколько дефектов открыто/подтверждено? | defects_by_status | «Нет данных.» |
| Analytics · TimeHistogram | Когда шли наблюдения? | клиентские корзины ≤300 записей (методология подписана, sample-size badge) | «Нет данных за период.» |
| Analytics · CoverageGrid | Где есть/нет покрытия? | coverage-ячейки (демо: эвристика, подписано) | нейтральные ячейки |
| JobDetail · Progress + stage-track | Что происходит с задачей? | job.progress/current_stage, polling 1.5s | стадий нет до старта |

Правила: числовые оси от нуля; тики постоянные (0/50/100% пика); единицы
подписаны под графиком; цвет семантический (band/severity/status), не
декоративный; легенда с образцами; tooltip — native title на барах/ячейках;
данные не интерполируются через пропуски; demo-данные маркированы.
Запрещены fake-charts и декоративные диаграммы без вопроса пользователя.

## 10. Брендовая согласованность двух сред

Общее: палитра-токены, типографика Oswald/Plex/JBM, радиусы 3–7px, плоские
поверхности, один shadow для оверлеев, семантика статусов, DEMO-маркировка,
иконки 24/1.6. Различия осознанные:
- **Showcase**: редакционная светлая сцена pipeline, крупная типографика,
  реальные фото (CC BY/CC0), scroll-повествование, specimens продукта.
- **Command Center**: тёмная плотная рабочая среда, минимум декора,
  данные и действия в приоритете; анимации только функциональные.
Промо-декор (scrub, parallax, reveal) не переносится в рабочие страницы.