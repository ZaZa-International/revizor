#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# SEC-4: infra-порты публикует только dev-override; тесты ходят на localhost.
compose() { docker compose -f docker-compose.yml -f docker-compose.dev.yml "$@"; }

echo "==> Запуск инфраструктуры для тестов (db, redis, s3, s3-init)..."
compose up -d db redis s3 s3-init

wait_healthy() {
    local service="$1" id status i
    for ((i = 1; i <= 60; i++)); do
        id="$(compose ps -q "$service")"
        status="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)"
        if [ "$status" = "healthy" ]; then
            return 0
        fi
        sleep 2
    done
    echo "ОШИБКА: сервис '$service' не стал healthy за 120 секунд." >&2
    compose logs --tail=50 "$service" >&2 || true
    return 1
}

wait_healthy db
wait_healthy redis
wait_healthy s3

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://mgts:mgts@localhost:5432/mgts_infra}"
# db 15 — изолированная логическая БД для тестов: conftest делает FLUSHDB,
# db 0 (dev-очередь RQ) затронута быть не должна.
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/15}"
export STORAGE_BACKEND=local
export STORAGE_LOCAL_PATH="${STORAGE_LOCAL_PATH:-/tmp/mgts-storage}"
export APP_ENV="${APP_ENV:-test}"
export ML_PROVIDER="${ML_PROVIDER:-mock}"

mkdir -p "$STORAGE_LOCAL_PATH"

echo "==> pytest (DATABASE_URL=$DATABASE_URL, STORAGE_BACKEND=$STORAGE_BACKEND)..."
cd backend
exec uv run pytest --cov=app --cov-report=term-missing "$@"
