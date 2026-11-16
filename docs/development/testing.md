# Тестирование

Backend полностью покрыт тестами: **262+ тестов** (число растёт в волне 3
исправлений аудита), все проходят. Тесты выполняются против **реальных**
PostgreSQL+PostGIS, Redis и объектного хранилища — никогда против SQLite или
«псевдо-БД». Это осознанное решение (см. [ADR-0011](../decisions/ADR-0011-real-infrastructure-tests.md)).

## Пирамида тестов

Количества ниже — на момент выпуска 0.1.0; волна 3 добавляет тесты
(regression security, concurrency, infra-down, лимиты тел/размерностей и т.д.).

| Уровень | Маркер | Кол-во (0.1.0) | Что проверяет | Внешние сервисы |
|---|---|---:|---|---|
| Unit | `unit` | 108 | Чистая доменная логика: risk scoring, dedup policy, condition-нормализация, state machine, геолокация, валидация загрузок, rate limiting, ML-провайдеры (mock/http на уровне клиента) | **Не требуются**: autouse-фикстура `clean_tables` пропускает тесты с маркером `unit` |
| Integration | `integration` | 35 | Репозитории и PostGIS-запросы, полный pipeline обработки, дедупликация на реальной БД, хранилище, экспорты, review-логика с БД, миграции очереди | PostGIS, Redis, storage |
| API | `api` | 83 | Эндпоинты `/api/v1/*` через ASGI-транспорт против реальной БД: auth/RBAC, uploads, jobs, assets, reviews, map, analytics, exports, ml, health | PostGIS, Redis, storage |
| Contract | `contract` | 36 | Контракт backend ↔ ML (JSON Schema ↔ Pydantic ↔ примеры) и контракт backend ↔ frontend (конверт ошибок, пагинация, порядок координат GeoJSON, сквозные сценарии) | PostGIS, Redis, storage |
| **Итого** | | **262+** | | |

Каталоги: `backend/tests/unit/`, `backend/tests/integration/`, `backend/tests/api/`,
`backend/tests/contracts/`, общие хелперы — `backend/tests/fixtures/`.

## Как запускать

### Полный прогон (рекомендуется)

```bash
make test          # = scripts/test.sh
```

`scripts/test.sh`:
1. поднимает инфраструктуру: `docker compose up -d db redis s3 s3-init`;
2. ждёт `healthy` у db/redis/s3 (до 120 с на сервис);
3. экспортирует тестовые переменные окружения (`STORAGE_BACKEND=local`,
   `APP_ENV=test`, `ML_PROVIDER=mock`, `REDIS_URL=redis://localhost:6379/15`
   и т.д.);
4. запускает `uv run pytest --cov=app --cov-report=term-missing` из `backend/`.

Аргументы пробрасываются в pytest: `make test ARGS=...` не поддерживается,
используйте `./scripts/test.sh -m unit -k dedup` напрямую.

### Выборочный прогон

Из каталога `backend/`. Unit-тесты автономны; для integration/api/contract
инфраструктура должна быть запущена (`docker compose up -d db redis s3 s3-init`):

```bash
uv run pytest -m unit                 # без внешних сервисов (clean_tables пропускает unit)
uv run pytest -m integration          # нужен docker compose db redis s3
uv run pytest -m api
uv run pytest -m contract
uv run pytest -m "integration or api or contract"
uv run pytest tests/unit/test_risk_scoring.py -k override
uv run pytest --cov=app --cov-report=term-missing
```

Маркеры объявлены в `backend/pyproject.toml` (`[tool.pytest.ini_options]`),
включён `--strict-markers`: незарегистрированный маркер — ошибка на этапе
сборки коллекции тестов.
`asyncio_mode = "auto"`, event loop — session-scoped: async-тесты не требуют
декораторов.

### Линтеры и типы (обязательно перед PR)

```bash
make lint          # = scripts/lint.sh: ruff check + ruff format --check + mypy app
make typecheck     # только mypy
make format        # автоформатирование: ruff format + ruff check --fix
```

## Требования к инфраструктуре

Сервисы из `docker-compose.yml`:

| Сервис | Образ | Зачем тестам |
|---|---|---|
| `db` | `postgis/postgis:16-3.4` | Реальная БД с PostGIS; тестовая БД создаётся автоматически |
| `redis` | `redis:7-alpine` | Rate limiting, очередь; тесты используют **db 15** |
| `s3` | `chrislusf/seaweedfs:latest` | S3-совместимое хранилище (поднимается скриптом; сами тесты по умолчанию пишут в local storage) |
| `s3-init` | `amazon/aws-cli` | Создаёт бакет `mgts-infra` |

Запуск: `docker compose up -d db redis s3 s3-init` (или `make bootstrap` для
первичной настройки).

**Важно:** autouse-фикстура `clean_tables` **пропускает тесты с маркером
`unit`** — unit-прогон не требует ни PostgreSQL, ни Redis, ни S3. Для
integration/api/contract фикстура зависит от `database` → `prepare_database`:
сессия создаёт/мигрирует тестовую БД и делает flush Redis. S3 для большинства
тестов не обязателен (local-бэкенд), кроме `test_s3_roundtrip`, которому нужен
живой S3: локально — `localhost:9000` (поднимает `scripts/test.sh`), в CI —
localstack на `localhost:4566` (`S3_ENDPOINT_URL`).

## Изоляция тестовой БД

`backend/tests/conftest.py` на импорте:

- берет `DATABASE_URL` (по умолчанию `postgresql+asyncpg://mgts:mgts@localhost:5432/mgts_infra`)
  и подменяет имя БД на **`mgts_infra_test`** — рабочая БД `mgts_infra` никогда
  не затрагивается. Имя переопределяется переменной **`TEST_DB_NAME`**;
- фикстура `prepare_database` (session): создаёт `mgts_infra_test`, если её нет,
  и применяет `alembic upgrade head` (subprocess, таймаут 180 с);
- Redis: `REDIS_URL` по умолчанию `redis://localhost:6379/15`, `FLUSHDB` перед
  прогоном — изолированная логическая БД;
- `STORAGE_BACKEND=local`, корень — свежий `tempfile.mkdtemp(prefix="mgts-test-storage-")`;
- `QUEUE_MODE=inline` — pipeline выполняется в процессе теста, без воркера;
- `ML_PROVIDER=mock` — детерминированный синтетический инференс;
- `APP_ENV=test`, фиксированный тестовый `JWT_SECRET_KEY`, bootstrap-админ
  `admin` / `admin-test-password`, rate-лимиты подняты до 10000/мин, чтобы не
  мешать тестам;
- фикстура `clean_tables` (**autouse**, на каждый тест; **пропускается для
  маркера `unit`**): `TRUNCATE ... RESTART IDENTITY CASCADE` всех таблиц
  public, кроме `alembic_version` и `spatial_ref_sys`. Каждый тест начинает
  с чистой схемы; миграции не пересоздаются.

### Параллельные прогоны

Несколько прогонов pytest на одной машине изолируются переменными окружения:

```bash
TEST_DB_NAME=mgts_infra_test_a REDIS_URL=redis://localhost:6379/14 ./scripts/test.sh -m api &
TEST_DB_NAME=mgts_infra_test_b REDIS_URL=redis://localhost:6379/13 ./scripts/test.sh -m contract &
```

- `TEST_DB_NAME` — отдельная тестовая БД на прогон (создаётся и мигрируется
  автоматически);
- `REDIS_URL` — отдельная логическая БД Redis на прогон (`FLUSHDB` в
  `prepare_database` иначе сотрёт данные соседнего прогона; **никогда не
  используйте db 0** — там dev-очередь RQ);
- storage изолируется автоматически: conftest создаёт свежий
  `tempfile.mkdtemp(prefix="mgts-test-storage-")` на каждый прогон.

## Обзор фикстур

`conftest.py`:

| Фикстура | Scope | Назначение |
|---|---|---|
| `settings` | session | `Settings` с тестовым окружением |
| `prepare_database` | session | Создание БД + миграции + flush Redis |
| `database` | session | `Database` (engine/session factory), dispose в конце |
| `clean_tables` | function, autouse | Очистка таблиц перед каждым тестом (пропускается для маркера `unit`) |
| `app` | function | `create_app()` с прожитым lifespan |
| `client` | function | `httpx.AsyncClient` поверх `ASGITransport` (без сети) |
| `admin_headers` | function | Bearer-заголовки bootstrap-админа |
| `operator_headers` / `viewer_headers` | function | Создаёт пользователя с ролью OPERATOR/VIEWER в БД и логинит |

`tests/fixtures/`:

- `helpers.py` — `ingest_image(...)` (загрузка через реальный `UploadService`),
  `create_queued_job(...)` и другие хелперы наполнения БД/хранилища;
- `media.py` — генерация **синтетических** JPEG (`make_jpeg_bytes`, варианты
  `good`/`dark`/`blurry` для quality gate) и метаданных съёмки. Реальные фото и
  персональные данные в тестах запрещены;
- `ml_stub.py` — детерминированный ML-стаб для pipeline-тестов (стабильные
  `detection_id` через `uuid5` от `storage_key`), включая сценарии ошибок.

## Coverage

- `pytest-cov`, источник — `app`, исключение — `app/workers/worker.py`
  (точка входа RQ-воркера; логика задач проверяется интеграционно через
  inline-очередь);
- локально: `./scripts/test.sh` печатает `term-missing`;
- CI: `--cov-report=xml`, артефакт `coverage` загружается в GitHub Actions;
- жёсткого порога `fail_under` сейчас нет — покрытие не должно падать при
  добавлении функциональности; новые модули ожидаются с тестами.

## CI (`.github/workflows/ci.yml`)

- **lint-typecheck**: `uv sync --frozen`, `ruff check`, `ruff format --check`, `mypy app`;
- **tests**: service containers `postgis/postgis:16-3.4`, `redis:7` и
  `localstack/localstack` (SERVICES=s3, порт 4566) с healthchecks;
  окружение job'а задаёт `S3_ENDPOINT_URL=http://localhost:4566` — S3-тесты
  (`test_s3_roundtrip`) выполняются против localstack, skip-условия не нужны;
  `alembic upgrade head`, затем `pytest -m unit` отдельно и
  `pytest -m "integration or api or contract"` с coverage;
- **migration roundtrip**: `alembic downgrade base && alembic upgrade head` —
  миграции обязаны быть обратимыми;
- **docker-build**: сборка образа backend;
- отдельно `.github/workflows/security.yml`: `pip-audit` — job падает на любой
  известной уязвимости в зависимостях (`continue-on-error: false`), по PR и
  еженедельно. План (волна 3): добавить флаг `--strict`, чтобы job падал также
  на зависимостях, которые не удалось проаудировать.

## Правила

1. **Никакого SQLite.** Geography/PostGIS-функции, частичные уникальные индексы
   и `TRUNCATE ... CASCADE` в SQLite не работают или работают иначе. Тест на
   SQLite даёт ложную уверенность.
2. **Никаких «фейковых» тестов.** Тест должен проверять реальное поведение:
   реальные запросы к БД, реальные файлы в хранилище, реальные HTTP-ответы
   через ASGI. Заглушки допустимы только на внешних границах (ML-провайдер,
   генерация синтетических медиа) и только детерминированные.
3. **Контрактные тесты валидируют JSON Schema.** `tests/contracts/test_ml_contract.py`
   проверяет согласованность `contracts/ml/*.schema.json` (draft 2020-12),
   эталонных примеров `contracts/ml/examples/` и Pydantic-моделей
   `app/schemas/ml.py` через `jsonschema`. Правка контракта без обновления
   схем/примеров/тестов ломает CI — это намеренно.
4. **Frontend-контракт** (`test_frontend_contract.py`): единый конверт ошибок
   `{"error": {code, message, details, request_id}}`, формат пагинации, порядок
   координат GeoJSON `(longitude, latitude)`, сквозные сценарии
   upload → job → observations → review.
5. **Изоляция.** Не пишите в `mgts_infra`, не используйте Redis db 0 в тестах
   (dev-очередь RQ; дефолт тестов — db 15, для параллельных прогонов — своя
   изолированная db на прогон), не рассчитывайте на состояние от предыдущего
   теста (`clean_tables` его удалит).
6. **Детерминизм.** Случайность — только с фиксированным seed; время — через
   явные параметры, не «сейчас» в проверках.

## Как добавить тесты для новой фичи

1. Определите уровень: чистая логика → `tests/unit/`; работа с БД/хранилищем/
   pipeline → `tests/integration/`; новый эндпоинт или изменение ответа →
   `tests/api/`; изменение формата обмена с ML/frontend → `tests/contracts/`.
2. Создайте `test_<модуль>.py` в соответствующем каталоге и поставьте
   `pytestmark = pytest.mark.<уровень>` (как в существующих файлах).
3. Используйте готовые фикстуры (`client`, `admin_headers`, `database`,
   `tests/fixtures/helpers.py`) вместо самодельной настройки окружения.
4. Медиа — только синтетические (`make_jpeg_bytes`); ML — mock или стаб из
   `ml_stub.py`.
5. Проверьте локально: `uv run pytest -m <маркер>` и `make lint`.
6. Если фича меняет контракт — обновите JSON Schema/примеры и контрактные тесты
   в том же PR (см. [adding-new-ml-provider.md](adding-new-ml-provider.md)).
7. Если фича требует новую таблицу/колонку — миграция Alembic обязана проходить
   roundtrip (`downgrade base` → `upgrade head`), CI это проверяет.

Смежные документы: [CONTRIBUTING.md](../../CONTRIBUTING.md) (Definition of Done),
[ADR-0011](../decisions/ADR-0011-real-infrastructure-tests.md).