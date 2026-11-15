# Устранение неполадок

## Конфликт портов (port is already allocated)

Симптом: `docker compose up` падает с `Bind for 0.0.0.0:5432 failed: port is
already allocated` (или 6379/9000/8000).

Причина: порт занят локальным сервисом (системный PostgreSQL/Redis) или другим
compose-проектом.

```bash
ss -ltnp | grep -E ':(5432|6379|9000|9333|8000)\b'   # кто занимает порт
docker ps --format '{{.Names}}\t{{.Ports}}'           # другие контейнеры
```

Решения: остановить локальный сервис (`sudo systemctl stop postgresql`), либо
`docker compose down` в старом проекте, либо опубликовать другие порты через
override-файл (`ports: ["5433:5432"]` и т.д.; тогда поправьте `DATABASE_URL`).

## Ошибка «extension postgis is not available» / type geometry does not exist

Причина: используется обычный образ `postgres` вместо `postgis/postgis`, либо
расширение не создано в базе.

- Убедитесь, что сервис `db` — `postgis/postgis:16-3.4` (как в
  `docker-compose.yml`). Если том `pgdata` остался от обычного postgres —
  пересоздайте его: `docker compose down && docker volume rm mgts-infra_pgdata`
  (данные будут удалены!).
- Проверка: `docker compose exec db psql -U mgts -d mgts_infra -c "SELECT extname FROM pg_extension;"` — должен быть `postgis`.
- При необходимости: `CREATE EXTENSION IF NOT EXISTS postgis;` (миграции делают
  это сами).

## Бакет S3 не создан (NoSuchBucket)

Симптом: загрузки файлов падают с `NoSuchBucket` / `The specified bucket does
not exist`.

Причина: `s3-init` не отработал (например, S3-сервер ещё не был готов или
неверные ключи).

```bash
docker compose logs s3-init
docker compose up s3-init        # повторить создание бакета (идемпотентно)
```

Проверка бакета:

```bash
docker compose exec s3 wget -qO- http://localhost:9000/
docker run --rm --network mgts-infra_default amazon/aws-cli --endpoint-url http://s3:9000 s3 ls s3://mgts-infra
```

Убедитесь, что `S3_BUCKET` в `.env` совпадает с тем, что создаёт `s3-init`,
а `S3_ENDPOINT_URL` указывает на работающий S3-сервис (`s3` в compose).

## Alembic: connection refused / could not connect to server

Симптом: `uv run alembic upgrade head` или старт backend падает с
`ConnectionRefusedError` / `could not connect to server`.

Причины и решения:

1. База не поднята: `docker compose ps db` — должен быть `healthy`;
   `docker compose up -d db` и подождать.
2. Неверный хост в `DATABASE_URL`: **с хоста** — `localhost:5432`,
   **из контейнера** — `db:5432` (compose переопределяет автоматически).
   `localhost` внутри контейнера указывает на сам контейнер.
3. Порт 5432 не опубликован или занят другим процессом (см. конфликт портов).
4. Неверные учётные данные: по умолчанию `mgts/mgts`, база `mgts_infra`.

Проверка: `docker compose exec db pg_isready -U mgts -d mgts_infra`.

## Worker не забирает задачи

Симптом: загрузки ставятся в очередь, но обработка не начинается.

Проверьте по порядку:

1. Worker запущен: `docker compose ps worker`, `docker compose logs -f worker`.
2. Совпадает имя очереди: `RQ_QUEUE_NAME` (по умолчанию `processing`) должно
   быть одинаковым у API и воркера.
3. Совпадает Redis: `REDIS_URL` у backend и worker должен указывать на один и
   тот же Redis (в compose — `redis://redis:6379/0`; с хоста — `localhost`).
   Частая ошибка: API в Docker пишет в контейнерный Redis, а воркер запущен с
   хоста и смотрит в другой экземпляр (или наоборот).
4. Очередь не пуста: `docker compose exec redis redis-cli LLEN rq:queue:processing`.
5. Задачи не падают сразу: смотрите traceback в логах воркера; проверьте
   доступность S3 (`S3_ENDPOINT_URL`) и ML-провайдера (`ML_PROVIDER`).
6. После правки кода воркер нужно перезапустить: `docker compose restart worker`
   (hot reload у воркера нет).

## Ошибки OpenCV (libGL / libgthread / libgomp)

Симптом: `ImportError: libGL.so.1: cannot open shared object file` или
`libgthread-2.0.so.0` / `libgomp.so.1` при импорте `cv2`.

Причина: не хватает системных библиотек. В образе backend они уже установлены
(`libglib2.0-0`, `libgomp1`; используется `opencv-python-headless`, поэтому
libGL не нужен). Если ошибка возникла вне образа (например, в голом
python:3.12-slim):

```bash
apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1
```

Убедитесь, что установлен именно `opencv-python-headless`, а не
`opencv-python` (последний тянет GUI-зависимости).

## Контейнер backend/worker перезапускается по кругу

```bash
docker compose logs --tail=100 backend worker
```

Частые причины:

- `JWT_SECRET_KEY must be set in production` — задан `APP_ENV=production` без
  `JWT_SECRET_KEY`; сгенерируйте: `openssl rand -hex 32`.
- Миграции не применяются (см. раздел про Alembic) — backend стартует только
  после успешного `alembic upgrade head`.
- `s3-init` не завершился успешно — backend/worker ждут его
  (`service_completed_successfully`); смотрите логи `s3-init`.

## Доступ к Docker без sudo

Если `docker compose` требует root: добавьте пользователя в группу `docker`
(`sudo usermod -aG docker $USER`, затем перелогиньтесь).
