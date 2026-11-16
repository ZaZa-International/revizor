#!/usr/bin/env bash
# Восстановление из резервной копии: pg_restore --clean --if-exists + S3 sync обратно.
# ВНИМАНИЕ: операция разрушающая — текущие данные БД и объекты бакета перезаписываются.
# Запуск: ./scripts/restore.sh backups/mgts_infra_<timestamp>.dump [--skip-s3]
# Требуется явное подтверждение (ввод RESTORE). Процедура restore-drill —
# в docs/operations/deployment.md.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '[restore %s] %s\n' "$(date '+%F %T')" "$*"; }

env_from_file() {
    local key="$1"
    if [ -f "$ROOT_DIR/.env" ]; then
        sed -n "s/^${key}=//p" "$ROOT_DIR/.env" | tail -n 1
    fi
}

usage() {
    echo "Использование: $0 <dump-file> [--skip-s3]" >&2
    exit 1
}

[ $# -ge 1 ] || usage
DUMP_FILE="$1"
SKIP_S3=false
if [ "${2:-}" = "--skip-s3" ]; then
    SKIP_S3=true
fi
[ -f "$DUMP_FILE" ] || { log "ОШИБКА: файл дампа не найден: $DUMP_FILE"; exit 1; }

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
PGUSER="${POSTGRES_USER:-mgts}"
PGDATABASE="${POSTGRES_DB:-mgts_infra}"
S3_BUCKET="${S3_BUCKET:-$(env_from_file S3_BUCKET)}"
S3_BUCKET="${S3_BUCKET:-mgts-infra}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-$(env_from_file S3_ACCESS_KEY)}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
S3_SECRET_KEY="${S3_SECRET_KEY:-$(env_from_file S3_SECRET_KEY)}"
S3_SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
S3_REGION="${S3_REGION:-$(env_from_file S3_REGION)}"
S3_REGION="${S3_REGION:-us-east-1}"
S3_INTERNAL_ENDPOINT_URL="${S3_INTERNAL_ENDPOINT_URL:-http://s3:9000}"
COMPOSE_NETWORK="${COMPOSE_NETWORK:-mgts-infra_default}"

echo "Будет выполнено:"
echo "  1. Остановка backend/worker (писатели)."
echo "  2. pg_restore --clean --if-exists в $PGDATABASE из $DUMP_FILE (текущие данные БД будут заменены)."
if [ "$SKIP_S3" = false ] && [ -d "$BACKUP_DIR/s3" ]; then
    echo "  3. s3 sync $BACKUP_DIR/s3 -> s3://$S3_BUCKET (объекты бакета будут перезаписаны)."
fi
echo "  4. Запуск backend/worker."
read -r -p "Введите RESTORE для подтверждения: " CONFIRM
if [ "$CONFIRM" != "RESTORE" ]; then
    log "Отменено пользователем."
    exit 1
fi

log "Останавливаю backend/worker..."
docker compose stop backend worker

log "Восстановление БД из $DUMP_FILE"
docker compose exec -T db pg_restore -U "$PGUSER" -d "$PGDATABASE" \
    --clean --if-exists --no-owner < "$DUMP_FILE"

if [ "$SKIP_S3" = false ] && [ -d "$BACKUP_DIR/s3" ]; then
    log "Синхронизация S3 обратно: $BACKUP_DIR/s3 -> s3://$S3_BUCKET"
    docker run --rm --network "$COMPOSE_NETWORK" \
        -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
        -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
        -e AWS_DEFAULT_REGION="$S3_REGION" \
        -v "$BACKUP_DIR/s3:/backup" \
        amazon/aws-cli --endpoint-url "$S3_INTERNAL_ENDPOINT_URL" \
        s3 sync /backup "s3://$S3_BUCKET"
else
    log "S3-восстановление пропущено (--skip-s3 или нет каталога $BACKUP_DIR/s3)."
fi

log "Запускаю backend/worker..."
docker compose start backend worker

log "Готово. Проверьте: curl -fsS http://localhost:8000/health/ready и выборочные данные в БД."
