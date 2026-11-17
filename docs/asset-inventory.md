# REVIZOR — Asset Inventory (Phase 5)

Дата: 17 ноября 2026. Все ассеты локальны; внешние CDN — только тайлы карты
(с fallback). Лицензии проверены по `frontend/public/assets/SOURCES.md`.
Действия: KEEP / REPLACE / REDESIGN / REMOVE / OPTIMIZE (выполнено в этом проходе).

## 1. Изображения

| ID | Путь | Размер | Формат | Назначение | Источник / лицензия | Качество | Действие |
|---|---|---|---|---|---|---|---|
| IMG-01 | public/assets/img/hero-night-768.webp | 17 KB | webp | Hero srcSet 768w | Wikimedia Commons, CC BY 4.0, Vyacheslav Argenberg | профессиональная аэросъёмка | KEEP |
| IMG-02 | …/hero-night-1280.webp | 36 KB | webp | Hero srcSet 1280w | то же | то же | KEEP |
| IMG-03 | …/hero-night-1920.webp | 70 KB | webp | Hero srcSet 1920w + preload | то же | то же | KEEP |
| IMG-04 | …/hero-night-2560.webp | 182 KB | webp | Hero srcSet 2560w | то же | то же | KEEP |
| IMG-05 | …/hero-night-lqip.webp | 132 B | webp | Hero background-placeholder | производное CC BY 4.0 | LQIP | KEEP |
| IMG-06 | …/aerial-day-768.webp | 39 KB | webp | InvisibleNetwork srcSet | CC BY 4.0, Argenberg | аэросъёмка | KEEP |
| IMG-07 | …/aerial-day-1280.webp | 89 KB | webp | то же 1280w | то же | то же | KEEP |
| IMG-08 | …/aerial-day-1920.webp | 242 KB | webp | то же 1920w | то же | то же | KEEP |
| IMG-09 | …/aerial-day-lqip.webp | 142 B | webp | не использовался | производное CC BY 4.0 | LQIP | **OPTIMIZE: подключён** как placeholder (VA-18) |
| IMG-10 | …/skyline-1280.webp | 193 KB | webp | FinalCta srcSet | CC0, Александр Сигачёв | панорама | KEEP |
| IMG-11 | …/skyline-1920.webp | 386 KB | webp | FinalCta 1920w | CC0 | то же | KEEP |
| IMG-12 | …/skyline-lqip.webp | 182 B | webp | не использовался | производное CC0 | LQIP | **OPTIMIZE: подключён** (VA-18) |
| IMG-13 | e2e/fixtures/survey-frame.jpg | — | jpeg | тестовая загрузка | синтетическая фикстура | тест | KEEP (не UI-ассет) |

Требования выполнены: локальное хранение, srcSet/sizes, lazy loading
(aerial-day, skyline, specimens), LQIP-placeholder без layout shift
(фиксированные aspect-ratio контейнеров), fallback при ошибке кадра
(EmptyState «Кадр недоступен»), атрибуция CC BY в футере.
Стоковые/AI-изображения не используются. Реальных кадров обследования нет —
demo-кадры синтетические и маркированы (см. §4).

## 2. Шрифты (OFL 1.1, локально)

| Семейство | Начертания | Subset-файлы | Действие |
|---|---|---|---|
| Oswald | 500, 600 | 8 woff2 | KEEP |
| Oswald | 400, 700 | 8 woff2 | **REMOVE** (не запрашивались CSS; VA-17) |
| IBM Plex Sans | 400/500/600/700 | 16 woff2 | KEEP |
| JetBrains Mono | 400/500/700 | 12 woff2 | KEEP; правила с font-weight 600 переведены на 500 (VA-16) |

Итого 36 woff2 (было 44). Preload: oswald-cyrillic-600, plex-cyrillic-400,
jetbrains-mono-cyrillic-500 (добавлен, VA-29).

## 3. SVG-реестр

| Файл | Тип | Назначение | Действие |
|---|---|---|---|
| public/favicon.svg | brand | знак сети, 4 места использования | KEEP |
| components/icons.tsx | A/B icons | 28 иконок (24 functional + 4 domain) + assetTypeIcon | KEEP; **REMOVE** 5 мертвых (Clock/Layers/Filter/Refresh/Menu), **ADD** IconMinus, IconTarget в использовании (VA-14/24) |
| components/charts.tsx | functional | HBarList/StackedBar (HTML), ColumnChart (**REDESIGN** HTML, VA-01/02), CoverageGrid (токены, VA-19), TimeHistogram; Sparkline **REMOVE** (VA-15) | выполнено |
| components/map/SchematicMap.tsx | functional | fallback карты; цвета → токены; zoom-иконки | выполнено (VA-19/24) |
| showcase/NetworkSvg.tsx | D illustration | схема «город→сеть», aria-hidden, подписана | KEEP; цвета → токены (VA-19) |
| app/LoginPage.tsx (LoginNetworkBg) | D decoration | brand-фон логина | KEEP; цвета → токены |
| showcase/scenes/Pipeline.tsx (8 Art*) | generic visuals | выдуманные значения в SVG | **REMOVE/REDESIGN**: заменены specimens реального продукта (VA-03) |
| showcase/scenes/Scenario.tsx (Dedup/History) | data visuals | захардкоженные SVG-значения | **REDESIGN**: HTML из demoData (VA-04) |
| demo/frames.ts | demo media | синтетические кадры | **REDESIGN**: дневная уличная сцена, точный chip bbox (VA-27/32) |
| components.css:273 (data-URI) | functional glyph | шеврон select | KEEP (цвет в URI — ограничение формата) |

## 4. Демо-медиа и данные

- `demo/data.ts` — детерминированный синтетический датасет (16 assets,
  29 observations, 9 defects, 3 routes, 3 uploads/jobs). KEEP: честный,
  маркированный, формы ответов зеркалят контракт.
- `demo/frames.ts` — дневная уличная сцена (дорога/тротуар/застройка),
  объект «стоит» на нижней границе bbox с тенью, chip шириной по фактическому
  тексту, footer «DEMO · СИНТЕТИЧЕСКИЙ КАДР · model». Цвета захардкожены
  (data-URL SVG не видит CSS-токены — документированное исключение).
- Showcase fallback-статистика теперь из датасета (16/29/9), не литералы
  18/34/12 (VA-05).
- Видеофайлов нет; загрузка видео — реальный flow API.

## 5. Удалённые ассеты (итог)

- 8 woff2 Oswald 400/700 + 8 @font-face.
- 5 мертвых иконок, Sparkline, QueryState (мертвый код).
- 8 SVG-«картинок» Pipeline + 2 SVG Scenario (заменены данными).
- `.dots` фейковое оконное обрамление (3 места + CSS).
- strokeDasharray="0" артефакт.

Новых внешних ассетов не добавлено; новые визуалы — собственные компоненты
и графика проекта. Зависимости не добавлялись.