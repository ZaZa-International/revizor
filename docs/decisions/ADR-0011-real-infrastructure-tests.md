# ADR-0011: Тесты на реальной инфраструктуре / Tests on real PostGIS, Redis and S3

- **Статус / Status:** Accepted
- **Дата:** 2026-11-15

## Контекст / Context

Ключевая логика системы завязана на возможности PostgreSQL/PostGIS:
geography-расстояния, bbox-фильтры, частичные уникальные индексы,
`TRUNCATE ... CASCADE`, CheckConstraint'ы, транзакционное поведение asyncpg.
Redis используется для rate limiting и очереди. Тесты на SQLite или моках
не проверяют эти механизмы и дают ложную уверенность («зелёные тесты —
сломанный продакшен»). При этом тесты должны быть изолированы от рабочих данных
и воспроизводимы в CI.

## Решение / Decision

1. **Никакого SQLite.** Integration/API/contract-тесты выполняются против
   **реального PostgreSQL+PostGIS** (`postgis/postgis:16-3.4`) и **реального
   Redis** (`redis:7`). Хранилище в тестах — local-бэкенд во временном каталоге
   (S3-реализация проверяется отдельным интеграционным тестом против реального
   S3-сервера).
2. **Выделенная тестовая БД `mgts_infra_test`**: создаётся автоматически
   (`CREATE DATABASE` при отсутствии) и мигрируется (`alembic upgrade head`)
   session-фикстурой `prepare_database`. Рабочая БД `mgts_infra` не затрагивается.
3. **Изоляция между тестами**: autouse-фикстура `clean_tables` делает
   `TRUNCATE ... RESTART IDENTITY CASCADE` всех таблиц public (кроме
   `alembic_version`, `spatial_ref_sys`) перед каждым тестом. Redis — отдельная
   логическая БД **15** с `FLUSHDB` перед прогоном.
4. **Детерминированное окружение тестов**: `QUEUE_MODE=inline` (pipeline в
   процессе теста), `ML_PROVIDER=mock` (синтетический инференс),
   `STORAGE_BACKEND=local` (tempdir), фиксированный тестовый JWT-секрет,
   bootstrap-админ, поднятые rate-лимиты, синтетические медиа
   (`tests/fixtures/media.py`).
5. **CI на service containers** (`.github/workflows/ci.yml`): job `tests`
   поднимает `postgis/postgis:16-3.4` и `redis:7` с healthchecks; unit-тесты
   гоняются отдельным шагом (service containers job уже запущены — autouse-фикстура
   требует БД и для unit), затем integration/api/contract с coverage;
   **migration roundtrip** (`alembic downgrade base && alembic upgrade head`)
   проверяет обратимость миграций; образ backend собирается отдельным job.
6. **Пирамида**: unit 108 / integration 35 / api 83 / contract 36 = 262 теста;
   маркеры `unit`/`integration`/`api`/`contract`, `--strict-markers`.
   Контрактные тесты валидируют JSON Schema ↔ Pydantic ↔ примеры (ML) и
   конверт ошибок/пагинацию/GeoJSON (frontend).

## Последствия / Consequences

- Тесты ловят реальные классы ошибок: SQL/гео-запросы, ограничения БД,
  поведение asyncpg (timezone-aware datetime), миграции, пагинацию.
- Прогон требует Docker (включая unit: autouse-фикстура создаёт/мигрирует
  тестовую БД и flush'ит Redis) — цена: локальный запуск чуть тяжелее,
  CI использует service containers вместо docker-in-docker.
- Изоляция гарантирована на уровне БД/Redis-индекса/tempdir; параллельные
  прогоны против одного сервера конфликтуют по `mgts_infra_test` — один прогон
  на окружение (осознанное ограничение; для параллели — отдельные БД/индексы).
- Migration roundtrip делает обратимость миграций обязательным свойством.
- Моки допустимы только на внешних границах (ML) и только детерминированные;
  «фейковые» тесты, не проверяющие реальное поведение, запрещены правилами
  (docs/development/testing.md).

## Рассмотренные альтернативы / Alternatives considered

1. **SQLite in-memory**: не поддерживает geography, частичные индексы,
   TRUNCATE CASCADE; другой диалект SQL — ложная уверенность; отклонено.
2. **Testcontainers (подъём контейнеров из pytest)**: гибко, но медленнее
   session-фикстур, требует Docker-in-Docker или socket-проброса в CI;
   service containers + авто-создание БД проще и быстрее; отклонено.
3. **Моки репозиториев/БД**: не проверяют SQL и ограничения; отклонено для
   integration/api (unit-тесты домена моков не требуют вовсе).
4. **Общая БД с рабочими данными без TRUNCATE**: взаимное загрязнение тестов и
   риск для данных; отклонено в пользу выделенной БД + очистки.