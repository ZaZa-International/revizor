# Источники ассетов

Все материалы хранятся локально. Внешние CDN не используются для кода и шрифтов.

## Фотографии (Wikimedia Commons)

| Файл | Оригинал | Лицензия | Автор |
|---|---|---|---|
| `hero-night-*.webp` | [Moscow, Aerial view over night Moscow, Russia.jpg](https://commons.wikimedia.org/wiki/File:Moscow,_Aerial_view_over_night_Moscow,_Russia.jpg) | CC BY 4.0 | Vyacheslav Argenberg |
| `aerial-day-*.webp` | [Moscow, Aerial view over Moscow, Russia.jpg](https://commons.wikimedia.org/wiki/File:Moscow,_Aerial_view_over_Moscow,_Russia.jpg) | CC BY 4.0 | Vyacheslav Argenberg |
| `skyline-*.webp` | [Moscow - Skyline - 2026-09 - p02.jpg](https://commons.wikimedia.org/wiki/File:Moscow_-_Skyline_-_2026-09_-_p02.jpg) | CC0 | Александр Сигачёв |

Производные варианты (resize/webp) распространяются под теми же лицензиями.
Атрибуция CC BY материалов также отображается в футере showcase.
Фотографии иллюстрируют предметную область (городская среда с высоты);
местоположение съёмки не выдаётся за данные системы.

## Шрифты (Google Fonts, SIL Open Font License 1.1)

- **Oswald** — display (начертания 500/600). © Vernon Adams, Kalapi Gajjar, Cyreal. OFL 1.1.
- **IBM Plex Sans** — интерфейс (400/500/600/700). © IBM Corp. OFL 1.1.
- **JetBrains Mono** — данные (400/500/700). © JetBrains s.r.o. OFL 1.1.

Файлы woff2 (subset cyrillic/cyrillic-ext/latin/latin-ext) получены через
Google Fonts CSS API и хранятся локально. Неиспользуемые начертания
(Oswald 400/700) удалены из репозитория. Тексты лицензий:
https://openfontlicense.org/open-font-license-official-text/

## Геоданные и демо

- Базовая карта (основной режим): локальный векторный стиль
  `public/styles/revizor-dark.json` (генератор `scripts/build-map-style.mjs`)
  поверх тайлов OpenFreeMap (https://openfreemap.org, © OpenMapTiles,
  © OpenStreetMap contributors, ODbL). Спрайты/глифы — OpenFreeMap.
- Fallback базовой карты: raster-тайлы Esri World Dark Gray
  (`server.arcgisonline.com`), © Esri, HERE, Garmin, FAO, NOAA, USGS.
  Бесплатно, без API-ключа. При недоступности тайлов — локальный схематичный
  SVG-режим (координатная сетка, без выдуманной географии). Атрибуция
  отображается на карте и в футере showcase.
- Демо-датасет `src/demo/` — синтетический, детерминированный, координаты
  условны (центр Москвы как демонстрационная зона). Маркируется DEMO в интерфейсе.
- Демо-кадры (`src/demo/frames.ts`) — собственная синтетическая графика:
  дневная уличная сцена с объектом в bbox, маркировка «DEMO · СИНТЕТИЧЕСКИЙ КАДР».
  Реальных кадров обследования в репозитории нет; при появлении реальных
  материалов demo-кадры заменяются через image_url/crop_url API.
- Showcase pipeline показывает реальные UI-компоненты продукта на демо-данных
  (specimens), декоративные SVG-иллюстрации стадий удалены.