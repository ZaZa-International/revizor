# Развёртывание

Стек рассчитан на запуск через Docker Compose (production-like). Образ backend
собирается из `backend/Dockerfile`: multi-stage, зависимости ставятся системно
из `uv.lock` (`uv export --frozen` + `uv pip install --system`), приложение
работает от непривилегированного пользователя `appuser` (uid 10001), не root.

## Запуск

```bash
cp .env.example .env   # отредактируйте секреты (см. ниже)
docker compose up -d --build
```

Compose поднимает: `db` (postgis/postgis:16-3.4), `redis` (7-alpine), `s3` (SeaweedFS),
одноразовый `s3-init` (создаёт бакет), `backend` (миграции + uvicorn) и
`worker` (`python -m app.workers.worker`). Backend и worker стартуют только
после того, как инфраструктура стала `healthy`, а `s3-init` завершился с
кодом 0.

Проверка:

```bash
docker compose ps
curl -fsS http://localhost:8000/health/ready
```

## Обязательные секреты и настройки для production

В `.env` (или в окружении) обязательно задайте:

| Переменная | Требование |
|---|---|
| `APP_ENV` | `production` |
| `JWT_SECRET_KEY` | **обязателен**: без него приложение не стартует в production. Генерация: `openssl rand -hex 32` |
| `BOOTSTRAP_ADMIN_PASSWORD` | сильный пароль первого администратора (создаётся при первом старте, если пользователей нет) |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | заменить `minioadmin` на стойкие значения; SeaweedFS в dev не проверяет S3-аутентификацию (см. ADR-0006) |
| `DATABASE_URL` | при внешнем PostgreSQL — свой URL; учтите, что compose переопределяет его на `db` |
| `DEBUG` | `false` |
| `LOG_FORMAT` | `json` |
| `CORS_ORIGINS` | только доверенные origin'ы фронтенда |

Примечания:

- Пароль PostgreSQL в `docker-compose.yml` зафиксирован как `mgts/mgts`
  (dev-контракт). Для production используйте внешний managed PostgreSQL или
  отдельный override-файл со своими учётными данными; не коммитьте его.
- `MAX_UPLOAD_SIZE_BYTES` по умолчанию 2 GiB — согласуйте с лимитами
  reverse proxy.
- `.env` закрыт в `.gitignore`; секреты передавайте через секрет-хранилище
  (CI/CD variables, Vault и т.п.), а не через репозиторий.

## Reverse proxy

Перед backend поставьте nginx/Traefik/Caddy с TLS:

- проксируйте на `backend:8000` (внутри сети compose) или `127.0.0.1:8000`;
- `client_max_body_size` (nginx) ≥ `MAX_UPLOAD_SIZE_BYTES`, иначе большие
  загрузки видео будут обрываться с 413;
- увеличьте `proxy_read_timeout`/`proxy_send_timeout` для долгих загрузок;
- порт 8000 наружу в production лучше не публиковать — только через proxy;
- порты 5432/6379/9000/9333 в production не должны быть доступны извне
  (уберите `ports` в override-файле или закройте firewall'ом);
- SeaweedFS master UI (9333) — только для администраторов, за TLS/auth proxy.

## Резервное копирование томов

Данные живут в именованных томах: `pgdata`, `redisdata`, `s3data`.

PostgreSQL (логический дамп, рекомендуется):

```bash
docker compose exec -T db pg_dump -U mgts -d mgts_infra -Fc > backup_$(date +%F).dump
# восстановление:
docker compose exec -T db pg_restore -U mgts -d mgts_infra --clean --if-exists < backup.dump
```

S3 (синхронизация бакета):

```bash
docker run --rm --network mgts-infra_default \
  -e AWS_ACCESS_KEY_ID=ACCESS -e AWS_SECRET_ACCESS_KEY=SECRET \
  -v /backup/mgts-infra:/backup/mgts-infra \
  amazon/aws-cli --endpoint-url http://s3:9000 s3 sync s3://mgts-infra /backup/mgts-infra
```

Redis содержит очередь и кэш — критичных данных нет, но при желании копируйте
RDB из тома `redisdata` (`docker compose exec redis redis-cli SAVE` + копия
`/data/dump.rdb`). Делайте бэкапы по расписанию (cron) и проверяйте
восстановление.

## Масштабирование воркеров

Worker не имеет HTTP-порта и состояния, поэтому масштабируется горизонтально:

```bash
docker compose up -d --scale worker=4
```

Все воркеры читают одну очередь RQ (`RQ_QUEUE_NAME=processing`) из Redis;
задачи распределяются автоматически. Следите за длиной очереди и
`RQ_JOB_TIMEOUT` (по умолчанию 1800 с). API (`backend`) масштабируйте
аналогично только вместе с балансировщиком (порт 8000 у него опубликован).

## Аудит зависимостей (CI)

Workflow `.github/workflows/security.yml` запускает `uv run pip-audit` на каждый
PR в `main` и еженедельно по расписанию (понедельник, 06:00 UTC). Режим
**строгий**: `continue-on-error: false`, любая известная уязвимость в
зависимостях роняет job и блокирует merge. Исключений для «неисправленных»
уязвимостей нет: если фикса ещё нет, оценивайте риск вручную и временно
отключайте проблемную функциональность/зависимость, а не аудит.

CI (`.github/workflows/ci.yml`): линтеры + mypy, юнит- и интеграционные тесты
на реальных PostGIS/Redis, roundtrip миграций (`downgrade base` → `upgrade head`)
и сборка Docker-образа.
