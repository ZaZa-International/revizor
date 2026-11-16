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

- **Oswald** — display. © Vernon Adams, Kalapi Gajjar, Cyreal. OFL 1.1.
- **IBM Plex Sans** — интерфейс. © IBM Corp. OFL 1.1.
- **JetBrains Mono** — данные. © JetBrains s.r.o. OFL 1.1.

Файлы woff2 (subset cyrillic/cyrillic-ext/latin/latin-ext) получены через
Google Fonts CSS API и хранятся локально. Тексты лицензий:
https://openfontlicense.org/open-font-license-official-text/

## Геоданные и демо

- Базовая карта: raster-тайлы CARTO dark (`basemaps.cartocdn.com`),
  © CARTO, © OpenStreetMap contributors. Используются только в live-карте
  с атрибуцией; при недоступности — локальный схематичный SVG-режим
  (координатная сетка, без выдуманной географии).
- Демо-датасет `src/demo/` — синтетический, детерминированный, координаты
  условны (центр Москвы как демонстрационная зона). Маркируется DEMO в интерфейсе.
- SVG-иллюстрации pipeline и кадра камеры — собственная графика проекта.