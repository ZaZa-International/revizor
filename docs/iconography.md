# REVIZOR — Iconography (Phase 4)

Дата: 17 ноября 2026. Набор: `frontend/src/components/icons.tsx`.
Стили: `components.css` (`.icon`, `.icon-sm`). Реестр и правила ниже.

## 1. Категории графики

### A. Functional UI icons
Навигация, действия, состояния. Единый собственный набор (стиль согласован,
смешения библиотек нет — подключение Lucide/Phosphor не потребовалось:
существующий набор последовательный и полный, обоснование в visual-research.md).

Правила:
- Сетка **24×24**, оптическая зона ~3–21, stroke **1.6**, linecap/linejoin round.
- Цвет только `currentColor`; семантика задаётся вызывающей стороной через
  CSS-токены (`var(--muted)`, `var(--crit)`…). Захардкоженных цветов в иконках нет.
- Размеры: `.icon` 18px (интерфейс), `.icon-sm` 14px (внутри кнопок/строк).
  Интерактивная область кнопки ≥32px (btn-sm padding обеспечивает).
- Outline (regular) по умолчанию; filled-варианты не вводятся без необходимости
  (принцип Fluent 2: regular — wayfinding, filled — выделенное состояние).
- `aria-hidden` по умолчанию; icon-only кнопки обязаны иметь `aria-label`.
- Именование по объекту/форме (IconWell, IconRoute), не по функции.

Реестр A (24):
| Иконка | Назначение | Где |
|---|---|---|
| IconOverview | навигация «Обзор» | AppShell rail |
| IconMap | навигация «Карта» | rail |
| IconAsset | объект (fallback типа) | rail, таблицы |
| IconObservation | наблюдение | rail |
| IconDefect | дефект (треугольник !) | rail, Overview |
| IconReview | проверка (check + дуга) | rail |
| IconJob | задача (список + часы) | rail, Jobs |
| IconRoute | маршрут (S-кривая) | rail, Routes |
| IconAnalytics | аналитика (бары) | rail |
| IconExport | выгрузка (стрелка в лоток) | rail, Exports |
| IconSearch | поиск | SearchInput |
| IconPlus / IconMinus | создать / zoom± | Routes, SchematicMap |
| IconClose | закрыть/отклонить | Dialog, Toast, Reviews |
| IconCheck | подтвердить | Reviews, Scenario |
| IconAlert | ошибка/пусто (круг !) | EmptyState, ErrorState |
| IconChevronDown/Left/Right | раскрытие/навигация | Hero, Pagination, детали |
| IconArrowRight | переход/CTA | Showcase, Overview |
| IconUpload | загрузка | Jobs dropzone |
| IconExternal | внешняя ссылка | ObservationDetail |
| IconTarget | сброс вида (crosshair) | SchematicMap |
| IconLogout | выход | AppShell |

### B. Domain symbols
Специализированные обозначения типов объектов. Та же сетка 24 и stroke 1.6,
узнаваемые силуэты, версии 18/14px читаемы:
| Символ | Силуэт | Тип |
|---|---|---|
| IconWell | два эллипса + корпус колодца | telecom_well |
| IconPole | стойка + траверса + провис | pole |
| IconCabinet | шкаф со створкой и ручкой | telecom_cabinet |
| IconCable | две провисающие линии | cable_line |

Маппинг `assetTypeIcon(type)` (icons.tsx) с fallback IconAsset. Используется
в таблицах, паспортах, инспекции карты, showcase. Новые типы объектов
добавляются в taxonomy backend и получают символ в той же системе.

### C. Status indicators
Статусы — компактные: `Status` (цвет + текст + форма square/diamond),
`Badge`, `Severity` (бар-метр S1–S5). Отдельная иконка к каждому текстовому
статусу НЕ добавляется (правило NN/g: избыточные иконки в однородных списках
вредят поиску). Форма маркера — второй носитель смысла после цвета.

### D. Illustrations / pictograms
- Showcase NetworkSvg — объясняющая схема «город → сеть», явно подписана
  «не географическая карта», draw-on привязан к scroll. KEEP.
- LoginPage background — сдержанный brand-фон, aria-hidden. KEEP.
- Demo-кадры (frames.ts) — синтетические материалы обследования, маркировка
  «DEMO · СИНТЕТИЧЕСКИЙ КАДР». REPLACE-ночь→день выполнена (VA-27).
- Pipeline «картинки» (8 SVG с выдуманными значениями) — **удалены**, заменены
  specimens реального продукта (VA-03).
- Крупные иллюстрации для простых действий запрещены; empty states — одна
  иконка Alert + текст + действие.

## 2. Выполненные действия

1. Найден и классифицирован каждый SVG (реестр — asset-inventory.md).
2. Удалены 5 мертвых иконок (Clock, Layers, Filter, Refresh, Menu); IconTarget
   возвращён в использование (сброс вида SchematicMap). Добавлен IconMinus
   (zoom−) в той же системе.
3. Удалён артефакт `strokeDasharray="0"` (IconRoute).
4. Текстовые glyphs zoom `+ − ⌂` заменены иконками Plus/Minus/Target.
5. Цвета inline SVG переведены на CSS-токены (NetworkSvg, SchematicMap,
   LoginPage, CoverageGrid); исключение — data-URL SVG кадров (изолированы
   от CSS) и WebGL-paint карты (зеркало geo/palette.ts, документировано).
6. Размеры проверены: 18/14px, таргеты кнопок ≥32px, toast-close 24px.
7. Accessibility: aria-hidden по умолчанию, aria-label на icon-only кнопках
   проверены во всех местах использования.
8. Consistency: единый stroke 1.6, currentColor, без filled-миксов.

## 3. Правила для будущих изменений

- Новая иконка: сетка 24, stroke 1.6, currentColor, aria-hidden; имя по объекту.
- Не смешивать сторонние icon-библиотеки с собственным набором.
- Не добавлять иконки к текстовым статусам в таблицах.
- Доменный символ — только через assetTypeIcon и в единой геометрии.
- Декоративный SVG обязан быть aria-hidden и нести объясняющую функцию
  (схема/фон), иначе удалить.