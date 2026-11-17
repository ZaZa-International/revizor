# REVIZOR — Visual QA, Scorecard & Final Report (Phases 13–15)

Дата: 17 ноября 2026. Backend и API-контракты не изменялись. Все изменения —
frontend + docs. Коммиты не выполнялись (без отдельного разрешения).

## 0. Метод и ограничение среды

**Модель не поддерживает просмотр изображений.** Визуальная проверка выполнена
программно в реальном браузере (Playwright): DOM-геометрия, контраст реального
текста, масштабы SVG, переполнения, клавиатурные сценарии, состояния компонентов;
плюс полный анализ кода. Скриншоты «до/после» приложены для человеческого ревью.
Субъективные оценки арт-дирекции ниже — по код-анализу и метрикам, не по пикселям;
они консервативны и требуют подтверждения человеком.

Инструменты:
- `frontend/scripts/visual-audit.mjs` (новый): обход 18 страниц/состояний на
  1440 и 390, контраст каждого видимого текстового узла, переполнения с учётом
  clipping, шрифты, probe графиков/сортировки/вкладок/тостов.
  Отчёты: `artifacts/audit-before/report.json`, `artifacts/audit-after/report.json`.
- `frontend/scripts/perf.mjs`: LCP/CLS/long tasks (production preview :4173).
- Существующие e2e (56 тестов) и unit (51 тест).

## 1. Cycle 1 — очевидные проблемы (найдены → исправлены)

Baseline-аудит и обход кода выявили (ID из visual-audit.md):

| Проблема | До | После |
|---|---|---|
| VA-01 подписи ColumnChart | SVG-text ~5.8px, растяжение ×5.28 (`preserveAspectRatio="none"`) | HTML-подписи 11px, без искажений (probe подтвердил) |
| VA-02 empty-ветка графиков | отсутствовала | «Нет данных» / «Нет данных за период» |
| VA-06 401 в консоли showcase | `enabled` утекал в query API (2 места) | 0 ошибок консоли без сессии |
| VA-05 fallback-числа showcase | 18/34/12 ≠ датасет 16/29/9 | точные значения из demoData |
| VA-07 контраст 2D/3D переключателя | 3.47:1 (2 нарушения DOM-аудита) | accent+accent-ink 9.7:1; 0 нарушений |
| VA-08 сортировка таблицы | только мышь (th onClick) | button.th-sort во всех 4 sortable-колонках, aria-sort |
| VA-09 Tabs | без keyboard/связи panel | roving tabindex, Arrow/Home/End, aria-controls (probe: ArrowRight переключает) |
| VA-10 Toast | без закрытия, error исчезал 5.2s | close-кнопка (probe: dismiss работает), hover/focus-пауза, error 10s |
| VA-11 отмена job | без подтверждения | confirm-диалог (probe: открывается, Escape закрывает, фокус на безопасной кнопке) |
| VA-12 upload «до 2 ГБ» | без size-check | клиентская проверка 2 GiB + серверный 413 |
| VA-13 Overview jobs | без ErrorState | ветка error + retry |
| VA-21 Dialog | без начального фокуса | фокус на первом поле / кнопке footer |
| VA-22 подтаблицы паспорта | мышь | tabIndex + Enter |
| VA-25 Exports ошибки | только toast | inline role=alert |
| VA-16 JBM 600 | 3 правила без face | переведены на 500 |
| VA-17 Oswald 400/700 | 8 мертвых woff2 | удалены (36 файлов) |
| VA-18 LQIP aerial/skyline | не подключены | подключены как placeholders |
| VA-29 mono preload | отсутствовал | добавлен |
| VA-14/15/26/28 мертвый код/декор | 6 иконок, Sparkline, QueryState, `.dots` | удалены; IconTarget/IconMinus в использовании |
| VA-24 zoom glyphs `+ − ⌂` | текст | иконки Plus/Minus/Target |
| VA-32 bbox chip ширина | эвристика len*9+130 | по фактическому тексту |

## 2. Cycle 2 — взгляд арт-директора (вопросы → решения)

- **Выглядит ли как продукт конкретной отрасли?** Pipeline showcase больше не
  набор универсальных SVG-картинок: 8 specimens реального продукта (загрузка,
  покадровый quality gate, кадр+bbox, координаты дедупликации с POSSIBLE_MATCH,
  дефект S4, факторы приоритета, решения оператора [1]–[4], timeline истории).
  Значения — из демо-датасета (probe: Δ 2,1 м / score 0,95; severity 4/5 →
  priority 70/100; damaged_cover → missing_cover S4→S5). Demo-кадры перерисованы
  как дневная уличная сцена объезда (VA-27) вместо ночного «мультфильма».
- **Есть ли собственная идентичность?** Сохранена: графит/бирюза, Oswald/Plex/JBM,
  редакционная светлая сцена, координатная строка, mono-данные. Промо-декор не
  перенесён в рабочую среду.
- **Не выглядит ли сгенерированным?** Удалены шаблонные элементы: фейковые
  оконные `.dots`, одинаковые картинки стадий, выдуманные числа в SVG.
- **Есть ли настоящие данные?** Live-режим работает от API (e2e @live против
  seeded backend); demo явно маркирован на каждом экране и в каждом specimen.
- **Можно ли убрать что-то без потери смысла?** Убрано: 5 иконок, Sparkline,
  QueryState, `.dots`, 8+2 SVG-иллюстраций, 8 шрифтовых файлов, 2 LQIP-заглушки
  подключены вместо удаления. Остальное несёт функцию (обосновано в anti-slop-audit).
- **Информационная иерархия:** KPI без иконок, attention-списки, плотные таблицы,
  карта как главный инструмент — сохранены; графики стали читаемыми.
- Дополнительные правки цикла 2: токенизация inline SVG (VA-19), hover-popup
  всех слоёв карты (VA-23), Scenario-визуалы HTML из данных (VA-04).

## 3. Метрики «до → после»

| Метрика | До | После |
|---|---|---|
| Контраст-нарушения реального текста (DOM, 18 страниц) | 2 | **0** |
| Ошибки консоли showcase без сессии | 1 (401) | **0** |
| Горизонтальные переполнения документа 360–1920 | 0 | **0** (e2e responsive) |
| Подписи графиков | ~6px, ×5.28 stretch | 11px HTML |
| Мертвые иконки / код / шрифты | 6 / 2 / 8 файлов | 0 / 0 / 0 |
| Клавиатурная сортировка / tabs / toast dismiss | нет / нет / нет | есть / есть / есть |
| Unit-тесты | 51 | **51 passed** |
| E2E (demo+live+map+responsive+robustness+showcase) | 56 | **56 passed (7.0m)** |
| tsc / production build | clean | clean |
| LCP (production preview) | — | showcase 1316ms · login 424ms · app 516ms · map 616ms (≤2.5s) |
| CLS | — | ≤0.002 (≤0.1) |
| Max long task | — | 360–601ms (инициализация карты/demo; задокументировано) |

## 4. Scorecard (Phase 14)

Шкала 0–10. Оценки — по код-анализу и DOM-метрикам (без просмотра пикселей),
консервативные. Критерии: VI — visual identity, CO — composition, TY — typography,
IH — information hierarchy, IC — iconography, IM — image quality, DV — data
visualization, DS — domain specificity, ID — interaction design, RQ — responsive.
10 не ставится: всегда есть остаток (см. §6).

| Страница | VI | CO | TY | IH | IC | IM | DV | DS | ID | RQ | Обоснование |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Showcase `/` | 8 | 8 | 8 | 7 | 8 | 8 | 7 | 8 | 7 | 7 | Сильная редакционная драматургия и реальные фото CC BY; specimens вместо картинок — отраслевая конкретика. Остаток: scrub-сцена требовательна к слабых устройствам, demo-кадры синтетические, субъективная доводка композиций не подтверждена глазами. |
| Login | 7 | 7 | 7 | 8 | 8 | 6 | — | 7 | 8 | 8 | Сдержанный brand-фон, health-статус, демо-вход; фон декоративен (обоснован), фото нет. |
| Overview | 7 | 7 | 7 | 8 | 8 | 6 | 7 | 8 | 7 | 8 | KPI без декора, attention-списки, мини-карта; DV — StackedBar читаем; нет own-фото (не нужно). |
| Map | 8 | 7 | 7 | 7 | 8 | 7 | 8 | 9 | 7 | 7 | Главный инструмент: 7 слоёв, 2D/3D, fallback-цепочка, URL-состояние, hover всех слоёв. Остаток: кольца дефектов поверх точек, длинная легенда, mobile-панели ниже карты. |
| Assets | 7 | 7 | 7 | 8 | 8 | — | 7 | 8 | 8 | 8 | Плотная таблица, keyboard-сортировка, mobile-карточки; DV — Severity-метры. |
| Asset Passport | 7 | 7 | 7 | 8 | 8 | 6 | 7 | 9 | 8 | 7 | Паспорт с факторами, историей, мини-картой; a11y вкладок/строк; фото — demo-кадры. |
| Observations | 7 | 7 | 7 | 7 | 8 | 6 | 7 | 8 | 7 | 6 | Кропы в таблице — материалы в центре; mobile — скролл 7 колонок (остаток VA-30). |
| Observation Detail | 7 | 7 | 7 | 8 | 8 | 6 | 7 | 9 | 7 | 7 | Кадр+bbox overlay, ML vs effective, dedup JSON, append-only история; кадр может истечь (честное сообщение). |
| Defects | 7 | 7 | 7 | 7 | 8 | — | 7 | 8 | 7 | 6 | Реестр severity desc; mobile-скролл (VA-30). |
| Defect Detail | 7 | 7 | 7 | 8 | 8 | 6 | 7 | 8 | 8 | 7 | Severity vs priority объяснены; edit role-gated; связанные наблюдения — с caveat (ограничение API). |
| Reviews | 8 | 8 | 7 | 8 | 8 | 6 | — | 9 | 8 | 7 | Рабочее место: очередь+кропы, 4 решения, клавиши 1–4, auto-advance, idempotency; submit без hotkey (осознанно). |
| Jobs | 7 | 7 | 7 | 8 | 8 | — | 7 | 8 | 8 | 6 | Реальный XHR-progress, size-check, drag-drop keyboard; mobile-скролл таблицы. |
| Job Detail | 7 | 7 | 7 | 8 | 8 | — | 8 | 9 | 8 | 7 | Настоящий pipeline monitor: stage-track 13 стадий, покадровые статусы, confirm-отмена, polling. |
| Routes | 7 | 7 | 7 | 7 | 8 | — | 6 | 8 | 7 | 6 | Создание с валидацией трека; DV минимальна (дистанция PostGIS). |
| Route Detail | 7 | 7 | 7 | 7 | 8 | 7 | 6 | 8 | 7 | 7 | Трек на карте; observation_count только первого job (ограничение контракта). |
| Analytics | 7 | 7 | 7 | 8 | 8 | — | 8 | 8 | 7 | 7 | 7 панелей с вопросами/единицами/методологией; графики читаемы, empty-ветки; client-buckets подписаны. |
| Exports | 7 | 7 | 7 | 7 | 8 | — | — | 7 | 8 | 7 | Фильтры+форматы, inline-ошибки, CSV BOM; XLSX live-only честно. |

Среднее по продукту ≈ 7.3/10 — зрелый рабочий уровень; до 9–10 не хватает
подтверждённой глазами субъективной доводки и реальных материалов обследования.

## 5. Финальный отчёт

### Что было плохо
- Графики: нечитаемые растянутые подписи (~6px), нет empty-состояний.
- Showcase Pipeline: 8 декоративных SVG с выдуманными значениями; Scenario —
  захардкоженные SVG-визуалы; fallback-числа не совпадали с датасетом.
- Баг: `enabled` в query-параметрах → 401 в консоли публичной страницы.
- A11y-пробелы: мышиная сортировка, Tabs без клавиатуры, toast без закрытия,
  диалоги без начального фокуса, подтаблицы без keyboard, контраст 2D/3D 3.47.
- Рабочие состояния: отмена job без confirm, upload без size-check, ошибки
  экспорта только toast, Overview jobs без error-ветки.
- Гигиена: мертвые иконки/код/шрифты, неиспользуемые LQIP, дубли цветов вне
  токенов, generic monospace в SVG, фейковые `.dots`.
- Demo-кадры: ночной «мультяшный» город вместо дневного уличного объезда.

### Что удалено
5 мертвых иконок, Sparkline, QueryState, 8 SVG-«картинок» Pipeline, 2 SVG
Scenario, `.dots` (3 места + CSS), 8 woff2 Oswald 400/700 + 8 @font-face,
strokeDasharray-артефакт. Ничего рабочего не удалено.

### Что заменено
- ColumnChart → HTML-колонки с осями и empty-ветками.
- Pipeline-визуалы → specimens реального продукта на demo-данных (8 форматов).
- Scenario-визуалы → HTML из demoData (dedup-координаты, timeline истории).
- Demo-кадры → дневная уличная сцена, объект у дороги, точный bbox-chip.
- Zoom glyphs → иконки; цвета inline SVG → CSS-токены; hover карты → все слои.
- Sort th → buttons; Tabs → WAI-ARIA; Toast → dismiss+pause; Dialog → focus;
  отмена job → confirm; upload → size-guard; Exports → inline error.

### Что оставлено и почему
Графитовая система, типографика, KPI без иконок, плоские панели, NetworkSvg
(объясняющая схема с дисклеймером), Login-фон (сдержанный brand), hero-bob
(affordance), reveal/scrub (обратимые, reduced-motion), demo-датасет (честный,
маркированный), клавиши 1–4 без submit-hotkey (осознанно), таблицы со скроллом
на mobile (enterprise-паттерн). Каждый вердикт — в anti-slop-audit.md.

### Новые ассеты и источники
Новых внешних ассетов нет. Добавлены: IconMinus, specimens-компоненты,
HTML-графики, дневные demo-кадры (собственная графика). Использованные
источники: Wikimedia Commons (CC BY 4.0 Argenberg; CC0 Сигачёв) — проверены,
атрибуция в футере; OFL-шрифты; OpenFreeMap/OSM (ODbL) + Esri fallback —
атрибуция на карте; SOURCES.md обновлён. Зависимости не добавлялись.

### Какие страницы улучшены
Все 17: Showcase (pipeline/scenario/кадры/числа/401), Login (токены), Overview
(error-ветка), Map (hover/контраст/токены), Assets/Passport (keyboard),
Observations/Defects/Details (кадры, токены), Reviews (toast), Jobs/JobDetail
(size-check/confirm), Routes, Analytics (графики), Exports (inline error).

### Тесты
- `npm run lint` (tsc): clean.
- `npm test`: 51 passed (детерминизм demo, фильтры, review-логика, 409, bbox).
- `npm run test:e2e`: 56 passed за 7.0m — showcase 6, demo 10, live 7,
  map-geospatial 9, map-failures 5, responsive 10, robustness 9. 0 JS-ошибок.
- `npm run build`: production OK (entry 10KB gz, vendor 66KB gz, maplibre
  218KB gz lazy, deck 232KB gz lazy).
- `visual-audit.mjs before/after`: 0 проблем / 0 ошибок после.
- `perf.mjs` (preview): LCP 424–1316ms, CLS ≤0.002.
- Probe-сценарии: sort-buttons, tabs ArrowRight, toast dismiss, cancel-confirm
  Escape, specimens data, chart 11px.

### Скриншоты до/после
- До: `frontend/artifacts/audit-before/` — 18 страниц/состояний × 1440/390
  (showcase-hero/network/pipeline/twin/scenario/platform/final, overview, map,
  assets, passport, observations, defects, reviews, reviews-card, jobs,
  job-detail, routes, analytics, exports + mobile).
- После: `frontend/artifacts/audit-after/` — тот же набор +
  `job-cancel-confirm-1440.png`. Отчёты: `report.json` в обеих папках.
- Просмотреть глазами: `npm run dev` → http://localhost:5173.

### Оставшиеся проблемы (честно)
1. **Нет vision-подтверждения**: субъективная композиционная доводка требует
   человеческого ревью скриншотов (ограничение среды).
2. **VA-30**: Observations/Defects/Jobs/Routes на mobile — горизонтальный скролл
   таблиц (карточки только у Assets). Допустимый enterprise-паттерн; улучшение —
   sticky-первая колонка или карточные режимы (отдельная задача).
3. **VA-31**: кольца дефектов поверх точек assets в совпадающих координатах;
   длинная легенда карты. Низкий приоритет.
4. Demo-кадры синтетические: реальных кадров обследования в репозитории нет;
   при появлении — заменяются через image_url/crop_url API.
5. Long task до 601ms при инициализации demo-данных/карты (лабораторно; INP в
   поле не измерен). MapLibre/deck chunks неустранимы для WebGL, загружаются lazy.
6. Ограничения backend-контракта (не изобретались): нет time-series endpoint
   (клиентские корзины ≤300, подписано); нет списка наблюдений дефекта;
   observation_count маршрута — только первый job; presigned URL истекают.
7. SchematicMap: keyboard-доступны только asset-узлы (остальные слои — мышь);
   tooltip-компонента нет (native title) — приемлемо.
8. RouteDetail/DefectDetail упрощения подписаны в UI.

## 6. Definition of Done — статус

- [x] Все страницы прошли аудит (17 маршрутов + состояния).
- [x] Бессмысленный декор удалён (обоснованно, anti-slop-audit).
- [x] Иконография — единая система (iconography.md).
- [x] SVG осознанно: functional/domain/illustration/decoration разделены.
- [x] Иллюстрации объясняют реальные процессы (specimens, схема сети).
- [x] CV-демонстрация на содержательных материалах (кадры+bbox+данные, DEMO).
- [x] Fake-charts устранены (все графики data-driven с empty-ветками).
- [x] Промостраница цельная; Command Center функционален.
- [x] Нет визуального дрейфа (токены, единый kit).
- [x] Адаптивность: 0 переполнений 360–1920.
- [x] Accessibility проверена (контраст 0 нарушений, keyboard, focus, ARIA).
- [x] Основные сценарии протестированы (56 e2e + 51 unit + probes).
- [x] Скриншоты до/после приложены.
- [x] Изменения подтверждены реальным запуском (dev + preview + live backend).
- [ ] Субъективный визуальный ревью человеком (ограничение среды — см. §0).