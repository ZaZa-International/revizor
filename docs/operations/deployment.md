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

В `.env` (или в окружении) обязательно задайте. Начиная с 0.2.0 эти требования
проверяются **валидатором конфигурации при старте** (`app/config.py`):
нарушение → отказ старта с понятной ошибкой, а не «тихая» небезопасная работа.

| Переменная | Требование |
|---|---|
| `APP_ENV` | `production` |
| `JWT_SECRET_KEY` | **обязателен**: сильный случайный секрет ≥ 32 символов. Пустое значение и placeholder'ы (`change-me*`, `changeme`, `secret`) отклоняются. Генерация: `openssl rand -hex 32`. При нескольких репликах API ключ должен быть **одинаковым во всех инстансах** (иначе токены не проходят проверку между репликами) |
| `BOOTSTRAP_ADMIN_PASSWORD` | **пусто** (bootstrap пропускается) либо сильный пароль ≥ 12 символов, не placeholder. Placeholder/короткий пароль в production → отказ старта. Админ создаётся только при первом старте с пустой таблицей пользователей; после — смените пароль и уберите переменную |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | значения `minioadmin` **отклоняются валидатором**; задайте стойкие ключи. SeaweedFS в dev не проверяет S3-аутентификацию (см. ADR-0006) — production-хранилище обязано быть с аутентификацией |
| `QUEUE_MODE` | `rq`. `inline` в production **запрещён** (валидатор): тяжёлая обработка не должна выполняться в процессе API |
| `CORS_ORIGINS` | только явные доверенные origin'ы фронтенда; `'*'` запрещён в любом окружении (CORS с credentials) |
| `DATABASE_URL` | при внешнем PostgreSQL — свой URL; учтите, что compose переопределяет его на `db` |
| `DEBUG` | `false`. `DEBUG` — флаг debug FastAPI (traceback'и в ответах об ошибках); допустим только в dev |
| `LOG_FORMAT` | `json` |
| `S3_PUBLIC_ENDPOINT_URL` | публичный URL S3 для presigned-ссылок (браузер не видит internal hostname `s3`); см. [storage.md](../integrations/storage.md) |

Примечания:

- Пароль PostgreSQL в `docker-compose.yml` зафиксирован как `mgts/mgts`
  (dev-контракт). Для production используйте внешний managed PostgreSQL или
  отдельный override-файл со своими учётными данными; не коммитьте его.
- `MAX_UPLOAD_SIZE_BYTES` по умолчанию 2 GiB, `MAX_JSON_BODY_BYTES` — 2 MiB;
  согласуйте с лимитами reverse proxy. Лимиты тел проверяются middleware
  **до аутентификации** (413), но edge-лимит nginx всё равно нужен.
- `.env` закрыт в `.gitignore`; секреты передавайте через секрет-хранилище
  (CI/CD variables, Vault и т.п.), а не через репозиторий.
- **План (волна 3, SEC-4):** базовый compose перестанет публиковать порты
  инфраструктуры (5432/6379/9000/9333) на хост — публикация только в явном
  dev-override. До этого закрывайте порты firewall'ом (см. ниже).

## Reverse proxy

Перед backend поставьте nginx/Traefik/Caddy с TLS:

- проксируйте на `backend:8000` (внутри сети compose) или `127.0.0.1:8000`;
- `client_max_body_size` (nginx) ≥ `MAX_UPLOAD_SIZE_BYTES`, иначе большие
  загрузки видео будут обрываться с 413;
- увеличьте `proxy_read_timeout`/`proxy_send_timeout` для долгих загрузок;
- порт 8000 наружу в production лучше не публиковать — только через proxy;
- порты 5432/6379/9000/9333 в production не должны быть доступны извне
  (уберите `ports` в override-файле или закройте firewall'ом);
- SeaweedFS master UI (9333) — только для администраторов, за TLS/auth proxy;
- security headers: backend сам отдаёт `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, CSP `frame-ancestors`; **HSTS
  (`Strict-Transport-Security`) задавайте на proxy** (например
  `add_header Strict-Transport-Security "max-age=31536000" always;` в nginx) —
  backend работает за TLS-терминацией и сам HSTS не проставляет;
- за proxy настройте `FORWARDED_ALLOW_IPS` uvicorn (доверенные адреса proxy),
  иначе rate limiting по IP будет видеть адрес proxy, а не клиента.

## Резервное копирование и восстановление

Данные живут в именованных томах: `pgdata`, `redisdata`, `s3data`.
Критичны PostgreSQL (реестр, история review/audit) и S3 (оригиналы, кадры,
кропы). Redis содержит очередь и кэш — восстановимых данных нет (при желании
копируйте RDB из тома `redisdata`: `docker compose exec redis redis-cli SAVE`
+ копия `/data/dump.rdb`).

### Скрипты

- **`scripts/backup.sh`** — логический дамп PostgreSQL (`pg_dump -Fc` через
  `docker compose exec -T db`) в `backups/mgts_infra_<YYYY-MM-DD_HHMMSS>.dump`
  + синхронизация бакета S3 в `backups/s3/` (`docker run amazon/aws-cli
  --endpoint-url http://s3:9000 s3 sync`). **Retention: последние 14 дампов**
  (`BACKUP_RETENTION`), более старые удаляются; в конце — сводка в лог
  (число дампов/объектов, размер). S3-копия инкрементальная (mirror), retention
  на неё не распространяется.
- **`scripts/restore.sh <dump-file> [--skip-s3]`** — восстановление:
  останавливает backend/worker, `pg_restore --clean --if-exists --no-owner`,
  затем `s3 sync` обратно в бакет (если есть `backups/s3/`), запускает сервисы.
  Операция разрушающая: требует явного подтверждения (ввод `RESTORE`).

Настройки через окружение: `BACKUP_DIR`, `BACKUP_RETENTION`, `POSTGRES_USER`,
`POSTGRES_DB`, `S3_BUCKET`, `S3_ACCESS_KEY`/`S3_SECRET_KEY` (по умолчанию
читаются из `.env`), `S3_INTERNAL_ENDPOINT_URL`, `COMPOSE_NETWORK`
(по умолчанию `mgts-infra_default` — имя сети compose-проекта `mgts-infra`).

```bash
./scripts/backup.sh                                   # снять копию
./scripts/restore.sh backups/mgts_infra_2026-11-16_030000.dump   # восстановить
```

### Расписание (cron)

```cron
# Ежедневно в 03:00, лог — в backups/backup.log
0 3 * * * cd /opt/revizor && ./scripts/backup.sh >> backups/backup.log 2>&1
```

### Offsite и шифрование (рекомендации)

- Каталог `backups/` содержит **неанонимизированные изображения и ПДн** —
  храните его с теми же мерами защиты, что и само хранилище.
- Копируйте дампы и S3-копию offsite (другой хост/регион, объектное хранилище
  с versioning): `aws s3 sync backups/ s3://<offsite-bucket>/revizor/` или
  rclone/restic. Дампы перед отправкой шифруйте (`age`/`gpg`), ключи — в
  секрет-хранилище, не рядом с копиями.
- Проверяйте целостность дампа: `pg_restore --list <file>` должен читаться.

### Restore-drill (проверка восстановления)

Бэкап, который ни разу не восстанавливали, бэкапом не считается. Процедура
(ежеквартально и после изменений схемы):

1. На отдельном окружении (или после `docker compose down` тестового стенда)
   поднимите инфраструктуру: `docker compose up -d db redis s3 s3-init`.
2. Возьмите свежий дамп из `backups/` и выполните
   `./scripts/restore.sh backups/<файл>.dump` (подтверждение `RESTORE`).
   Для проверки только БД — `--skip-s3`.
3. Проверьте: `curl -fsS http://localhost:8000/health/ready`; количество
   строк в ключевых таблицах (`uploads`, `assets`, `observations`, `reviews`)
   совпадает с ожидаемым на момент дампа; выборочный файл открывается по
   presigned-ссылке.
4. Зафиксируйте дату и результат drill в журнале эксплуатации.

> Ручной эквивалент (если скрипты недоступны):
> `docker compose exec -T db pg_dump -U mgts -d mgts_infra -Fc > backups/mgts_infra_$(date +%F).dump`
> и восстановление тем же именем файла:
> `docker compose exec -T db pg_restore -U mgts -d mgts_infra --clean --if-exists < backups/mgts_infra_$(date +%F).dump`.

## Масштабирование воркеров

Worker не имеет состояния и масштабируется горизонтально:

```bash
docker compose up -d --scale worker=4
```

Все воркеры читают одну очередь RQ (`RQ_QUEUE_NAME=processing`) из Redis;
задачи распределяются автоматически. Следите за длиной очереди и
`RQ_JOB_TIMEOUT` (по умолчанию 1800 с). API (`backend`) масштабируйте
аналогично только вместе с балансировщиком (порт 8000 у него опубликован)
и **общим `JWT_SECRET_KEY`** во всех репликах.

Наблюдаемость воркеров (0.2.0):

- каждый worker поднимает Prometheus endpoint на `WORKER_METRICS_PORT`
  (по умолчанию **9100**) — scrape'ьте его отдельно от API `/metrics`;
  при `--scale worker=N` публикуйте порты через override или используйте
  service discovery;
- зависшие job'ы автоматически восстанавливает stale-sweeper (порог
  `RQ_JOB_TIMEOUT + STALE_JOB_GRACE_SECONDS`, по умолчанию 1920 с) —
  runbook в [troubleshooting.md](troubleshooting.md);
- **план (волна 3):** `stop_grace_period` worker в compose ≥ бюджета задачи,
  чтобы warm shutdown успевал завершить in-flight job (сейчас SIGKILL через
  10 с; backstop — stale-sweeper).

## Аудит зависимостей (CI)

Workflow `.github/workflows/security.yml` запускает `uv run pip-audit` на каждый
PR в `main` и еженедельно по расписанию (понедельник, 06:00 UTC). Job падает
на **любой известной уязвимости** в зависимостях (`continue-on-error: false`)
и блокирует merge. Исключений для «неисправленных» уязвимостей нет: если фикса
ещё нет, оценивайте риск вручную и временно отключайте проблемную
функциональность/зависимость, а не аудит. План (волна 3): флаг `--strict` —
падение также на зависимостях, которые не удалось проаудировать.

CI (`.github/workflows/ci.yml`): линтеры + mypy, юнит- и интеграционные тесты
на реальных PostGIS/Redis/S3 (localstack), roundtrip миграций
(`downgrade base` → `upgrade head`) и сборка Docker-образа.
