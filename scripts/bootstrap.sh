#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# SEC-4: базовый compose не публикует infra-порты; для host-разработки
# (psql/redis-cli/S3 UI, тесты, seed) всегда нужен dev-override.
compose() { docker compose -f docker-compose.yml -f docker-compose.dev.yml "$@"; }

for cmd in uv docker; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ОШИБКА: команда '$cmd' не найдена." >&2
        case "$cmd" in
            uv) echo "Установите uv: https://docs.astral.sh/uv/getting-started/installation/" >&2 ;;
            docker) echo "Установите Docker Engine 29+ с плагином Compose v2+." >&2 ;;
        esac
        exit 1
    fi
done

if ! docker compose version >/dev/null 2>&1; then
    echo "ОШИБКА: требуется Docker Compose v2+ (команда 'docker compose')." >&2
    exit 1
fi

if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Создан .env из .env.example (проверьте секреты перед production)."
fi

echo "==> Установка зависимостей backend (uv sync)..."
(cd backend && uv sync)

echo "==> Запуск инфраструктуры: db, redis, s3, s3-init (base + dev-override)..."
echo "    NOTE: docker-compose.dev.yml публикует 5432/6379/9000/9333 на host."
echo "    Базовый docker-compose.yml (без override) infra-порты НЕ публикует (SEC-4)."
compose up -d db redis s3 s3-init

wait_healthy() {
    local service="$1" id status i
    for ((i = 1; i <= 60; i++)); do
        id="$(compose ps -q "$service")"
        status="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)"
        if [ "$status" = "healthy" ]; then
            echo "    $service: healthy"
            return 0
        fi
        sleep 2
    done
    echo "ОШИБКА: сервис '$service' не стал healthy за 120 секунд." >&2
    compose logs --tail=50 "$service" >&2 || true
    return 1
}

echo "==> Ожидание готовности сервисов..."
wait_healthy db
wait_healthy redis
wait_healthy s3

echo "==> Ожидание создания бакета (s3-init)..."
init_ok=0
for ((i = 1; i <= 30; i++)); do
    id="$(compose ps -aq s3-init)"
    state="$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo missing)"
    if [ "$state" = "exited" ]; then
        code="$(docker inspect -f '{{.State.ExitCode}}' "$id")"
        if [ "$code" != "0" ]; then
            echo "ОШИБКА: s3-init завершился с кодом $code." >&2
            compose logs s3-init >&2 || true
            exit 1
        fi
        init_ok=1
        break
    fi
    sleep 2
done
if [ "$init_ok" != "1" ]; then
    echo "ОШИБКА: s3-init не завершился за 60 секунд." >&2
    exit 1
fi
echo "    s3-init: бакет готов"

echo "==> Применение миграций (alembic upgrade head)..."
(cd backend && uv run alembic upgrade head)

cat <<'EOF'

Готово! Инфраструктура поднята, миграции применены.

Дальнейшие шаги:
  make dev        — запуск API + worker с hot reload (http://localhost:8000/docs)
  make up         — запуск всего стека в фоне (базовый compose: infra-порты закрыты,
                    для локального доступа к db/redis/s3 используйте dev-override)
  make seed       — загрузка демо-данных
  make test       — тесты
  make lint       — линтеры и mypy

Локальный стек с портами infra на host:
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

Swagger UI:  http://localhost:8000/docs
S3 (SeaweedFS) master UI: http://localhost:9333 (dev-override)
EOF
