# Локальная разработка

## Требования

- Docker Engine 29+ и Docker Compose v2+ (`docker compose`)
- [uv](https://docs.astral.sh/uv/) (менеджер зависимостей Python)
- Python 3.12 (uv установит сам при `uv sync`)

## Быстрый старт

```bash
make bootstrap   # или ./scripts/bootstrap.sh
```

Скрипт:

1. проверяет наличие `uv` и `docker compose`;
2. создаёт `.env` из `.env.example`, если его нет;
3. ставит зависимости backend (`uv sync`);
4. поднимает инфраструктуру: `db` (PostgreSQL 16 + PostGIS 3.4), `redis`, `s3` (SeaweedFS) и
   одноразовый `s3-init` (создаёт бакет `mgts-infra`);
5. ждёт, пока сервисы станут `healthy`;
6. применяет миграции: `uv run alembic upgrade head`.

Дальше:

```bash
make dev    # API + worker с hot reload, foreground (Ctrl+C — остановить)
make up     # весь стек в фоне, со сборкой образа backend
make down   # остановить стек
make logs   # логи всех сервисов
```

## Hot reload

`make dev` (он же `scripts/dev.sh`) запускает
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.
Dev-оверрайд монтирует `./backend` в `/app` контейнера и запускает
`uvicorn app.main:app --reload` — изменения кода применяются без пересборки образа.
Worker монтируется так же; после изменения кода воркера перезапустите его:
`docker compose restart worker`.

Зависимости в образе установлены системно (`uv pip install --system`), поэтому
внутри контейнера работают обычные `python`, `uvicorn`, `alembic` без `uv`.
Если вы добавили зависимость в `backend/pyproject.toml`, пересоберите образ:
`docker compose build backend worker` (или `make up`).

## Порты

| Сервис            | Порт  | Назначение                          |
|-------------------|-------|-------------------------------------|
| backend (API)     | 8000  | FastAPI, Swagger UI: `/docs`        |
| db (PostGIS)      | 5432  | PostgreSQL, пользователь `mgts`     |
| redis             | 6379  | Redis / очередь RQ                  |
| s3 (SeaweedFS)   | 9000  | S3-совместимое хранилище            |
| s3 (master UI)   | 9333  | SeaweedFS master UI                 |

Полезные эндпоинты API:

- Swagger UI: <http://localhost:8000/docs>
- Health: `/health/live`, `/health/ready`, `/health`
- Метрики Prometheus: `/metrics`

## Переменные окружения

Все переменные перечислены в `.env.example` (значения по умолчанию безопасны для
локальной разработки). Ключевые:

| Переменная | По умолчанию | Описание |
|---|---|---|
| `APP_ENV` | `development` | `development` / `production` / `test` |
| `DATABASE_URL` | `postgresql+asyncpg://mgts:mgts@localhost:5432/mgts_infra` | в compose переопределяется на хост `db` |
| `REDIS_URL` | `redis://localhost:6379/0` | в compose — хост `redis` |
| `STORAGE_BACKEND` | `s3` | `s3` или `local` (файлы в `STORAGE_LOCAL_PATH`) |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | в compose — `http://s3:9000` |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | `minioadmin` | dev-значения по умолчанию |
| `S3_BUCKET` | `mgts-infra` | создаётся сервисом `s3-init` |
| `ML_PROVIDER` | `mock` | `mock` или `http` (`ML_HTTP_BASE_URL`) |
| `JWT_SECRET_KEY` | пусто | в dev генерируется случайный; в production **обязателен** |
| `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` | `admin` / пусто | если пароль задан, админ создаётся при первом старте (когда пользователей нет) |
| `RQ_QUEUE_NAME` | `processing` | имя очереди воркера |
| `LOG_FORMAT` | `json` | в dev-оверрайде — `console` |

Важно: `docker-compose.yml` переопределяет `DATABASE_URL`, `REDIS_URL` и
`S3_ENDPOINT_URL` для контейнеров (хосты `db`, `redis`, `s3`). Значения из
`.env` с `localhost` используются при запуске вне Docker (тесты, alembic с хоста).

Настоящий `.env` никогда не коммитится (закрыт в `.gitignore`).

## Миграции

Конфигурация: `backend/alembic.ini`, миграции: `backend/migrations`.
Все команды — из каталога `backend/`:

```bash
cd backend
uv run alembic upgrade head                 # применить (или make migrate из корня)
uv run alembic revision --autogenerate -m "описание"   # новая миграция
uv run alembic downgrade -1                 # откатить одну
uv run alembic downgrade base               # откатить всё
```

В Docker миграции применяются автоматически при старте контейнера `backend`
(`alembic upgrade head && uvicorn ...`).

## Демо-данные и OpenAPI

```bash
make seed      # cd backend && uv run python ../scripts/seed_demo.py
make openapi   # cd backend && uv run python ../scripts/export_openapi.py
```

## Тесты

Маркеры: `unit`, `integration`, `api`, `contract`.

```bash
# Юнит-тесты — без внешних сервисов:
cd backend && uv run pytest -m unit

# Полный прогон (инфраструктура поднимается автоматически, STORAGE_BACKEND=local):
make test                       # scripts/test.sh
./scripts/test.sh -m unit       # можно передать любые аргументы pytest
./scripts/test.sh -m "integration or api"
```

`scripts/test.sh` поднимает `db`, `redis`, `s3`, `s3-init`, ждёт готовности,
экспортирует `DATABASE_URL`/`REDIS_URL` на `localhost`, `STORAGE_BACKEND=local`,
`STORAGE_LOCAL_PATH=/tmp/mgts-storage` и запускает pytest с покрытием.
Интеграционные/API-тесты требуют реальных PostgreSQL+PostGIS и Redis.

## Линтеры и типы

```bash
make lint       # ruff check . && ruff format --check . && mypy app
make format     # ruff format . && ruff check --fix .
make typecheck  # mypy app
```

Pre-commit (опционально): `cd backend && uv run pre-commit install` — хуки
выполняют те же проверки через `uv` (конфиг `.pre-commit-config.yaml` в корне).
