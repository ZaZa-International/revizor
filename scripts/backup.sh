#!/usr/bin/env bash
# Резервное копирование: логический дамп PostgreSQL (pg_dump -Fc) + синхронизация
# S3-бакета в локальный каталог. Retention: последние N дампов (по умолчанию 14).
# Запуск: ./scripts/backup.sh (инфраструктура compose должна быть запущена).
# Переменные: BACKUP_DIR, BACKUP_RETENTION, POSTGRES_USER, POSTGRES_DB,
#             S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION,
#             S3_INTERNAL_ENDPOINT_URL, COMPOSE_NETWORK.
# Значения S3_* по умолчанию берутся из .env (если есть), затем dev-дефолты.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '[backup %s] %s\n' "$(date '+%F %T')" "$*"; }

env_from_file() {
    local key="$1"
    if [ -f "$ROOT_DIR/.env" ]; then
        sed -n "s/^${key}=//p" "$ROOT_DIR/.env" | tail -n 1
    fi
}

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION="${BACKUP_RETENTION:-14}"
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

mkdir -p "$BACKUP_DIR" "$BACKUP_DIR/s3"

TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/${PGDATABASE}_${TIMESTAMP}.dump"

log "Дамп PostgreSQL: $PGDATABASE -> $DUMP_FILE"
docker compose exec -T db pg_dump -U "$PGUSER" -d "$PGDATABASE" -Fc > "$DUMP_FILE"
if [ ! -s "$DUMP_FILE" ]; then
    log "ОШИБКА: дамп пуст, удаление неполного файла."
    rm -f "$DUMP_FILE"
    exit 1
fi
log "Дамп готов: $(du -h "$DUMP_FILE" | cut -f1)"

log "Синхронизация S3: s3://$S3_BUCKET -> $BACKUP_DIR/s3"
docker run --rm --network "$COMPOSE_NETWORK" \
    -e AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
    -e AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" \
    -e AWS_DEFAULT_REGION="$S3_REGION" \
    -v "$BACKUP_DIR/s3:/backup" \
    amazon/aws-cli --endpoint-url "$S3_INTERNAL_ENDPOINT_URL" \
    s3 sync "s3://$S3_BUCKET" /backup

log "Retention: храню последние $RETENTION дампов, остальные удаляю."
pruned=0
while IFS= read -r old_dump; do
    rm -f -- "$old_dump"
    pruned=$((pruned + 1))
done < <(ls -1t "$BACKUP_DIR/${PGDATABASE}_"*.dump 2>/dev/null | tail -n +"$((RETENTION + 1))")

kept="$(ls -1 "$BACKUP_DIR/${PGDATABASE}_"*.dump 2>/dev/null | wc -l)"
s3_objects="$(find "$BACKUP_DIR/s3" -type f | wc -l)"
log "Итого: дампов=$kept (удалено=$pruned), объектов S3=$s3_objects, размер каталога=$(du -sh "$BACKUP_DIR" | cut -f1)"
log "Готово. Проверьте восстановление: ./scripts/restore.sh (см. docs/operations/deployment.md)."
