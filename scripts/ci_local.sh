#!/usr/bin/env bash
# Полное локальное воспроизведение CI (lint -> typecheck -> unit -> infra ->
# миграции -> integration/api/contract -> roundtrip -> контракты -> docker build
# -> smoke). Опционально: --with-audit (pip-audit --strict).
#
# Требования: uv, docker compose v2+, node/npx (для TS-клиента), запущенный
# Docker daemon. Infra поднимается через base + dev-override (порты на host).
# Тома НЕ удаляются; стек после прогона остаётся запущенным.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WITH_AUDIT=0
for arg in "$@"; do
    case "$arg" in
        --with-audit) WITH_AUDIT=1 ;;
        *) echo "Неизвестный аргумент: $arg (поддерживается --with-audit)" >&2; exit 2 ;;
    esac
done

compose() { docker compose -f docker-compose.yml -f docker-compose.dev.yml "$@"; }

DEV_DATABASE_URL="postgresql+asyncpg://mgts:mgts@localhost:5432/mgts_infra"
TEST_DB_NAME="${TEST_DB_NAME:-mgts_infra_test}"
TEST_DATABASE_URL="postgresql+asyncpg://mgts:mgts@localhost:5432/${TEST_DB_NAME}"
TEST_REDIS_URL="redis://localhost:6379/15"

STEP_NO=0
declare -a STEP_NAMES=() STEP_RESULTS=()

run_step() {
    local name="$1" rc=0
    shift
    STEP_NO=$((STEP_NO + 1))
    echo ""
    echo "==> [${STEP_NO}] ${name}"
    "$@" || rc=$?
    STEP_NAMES+=("$name")
    if [ "$rc" -eq 0 ]; then
        STEP_RESULTS+=("PASS")
    else
        STEP_RESULTS+=("FAIL")
        echo "    STEP FAILED (exit ${rc}): ${name}" >&2
    fi
}

wait_healthy() {
    local service="$1" id status i
    for ((i = 1; i <= 90; i++)); do
        id="$(compose ps -q "$service")"
        status="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)"
        if [ "$status" = "healthy" ]; then
            echo "    $service: healthy"
            return 0
        fi
        sleep 2
    done
    echo "ОШИБКА: сервис '$service' не стал healthy за 180 секунд." >&2
    compose logs --tail=50 "$service" >&2 || true
    return 1
}

wait_s3_init() {
    local id state code i
    for ((i = 1; i <= 30; i++)); do
        id="$(compose ps -aq s3-init)"
        state="$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || echo missing)"
        if [ "$state" = "exited" ]; then
            code="$(docker inspect -f '{{.State.ExitCode}}' "$id")"
            if [ "$code" != "0" ]; then
                echo "ОШИБКА: s3-init завершился с кодом $code." >&2
                compose logs s3-init >&2 || true
                return 1
            fi
            echo "    s3-init: бакет готов"
            return 0
        fi
        sleep 2
    done
    echo "ОШИБКА: s3-init не завершился за 60 секунд." >&2
    return 1
}

step_ruff_check() { (cd backend && uv run ruff check .); }
step_ruff_format() { (cd backend && uv run ruff format --check .); }
step_mypy() { (cd backend && uv run mypy app); }
step_unit() { (cd backend && uv run pytest -m unit); }

step_infra() {
    compose up -d db redis s3 s3-init
    wait_healthy db
    wait_healthy redis
    wait_healthy s3
    wait_s3_init
}

step_migrate_dev() {
    (cd backend && DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head)
}

step_integration() {
    (cd backend \
        && DATABASE_URL="$DEV_DATABASE_URL" \
           TEST_DB_NAME="$TEST_DB_NAME" \
           REDIS_URL="$TEST_REDIS_URL" \
           STORAGE_BACKEND=local \
           STORAGE_LOCAL_PATH="${STORAGE_LOCAL_PATH:-/tmp/mgts-storage}" \
           APP_ENV=test \
           ML_PROVIDER=mock \
           uv run pytest -m "integration or api or contract")
}

step_roundtrip() {
    (cd backend \
        && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic downgrade base \
        && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head)
}

step_openapi_drift() {
    if [ ! -f scripts/check_openapi.py ]; then
        echo "ОШИБКА: scripts/check_openapi.py отсутствует (артефакт Contracts-агента)." >&2
        return 1
    fi
    (cd backend && uv run python ../scripts/check_openapi.py)
}

step_ts_client() {
    if [ ! -f contracts/typescript/schema.d.ts ]; then
        echo "ОШИБКА: contracts/typescript/schema.d.ts отсутствует (артефакт Contracts-агента)." >&2
        return 1
    fi
    npx --yes openapi-typescript contracts/openapi/openapi.json -o /tmp/schema.d.ts
    diff -u contracts/typescript/schema.d.ts /tmp/schema.d.ts
}

step_docker_build() { compose build backend; }

step_smoke() {
    if [ ! -f scripts/smoke.sh ]; then
        echo "ОШИБКА: scripts/smoke.sh отсутствует (артефакт QA-агента)." >&2
        return 1
    fi
    compose up -d backend worker
    wait_healthy backend
    wait_healthy worker
    (cd backend \
        && DATABASE_URL="$DEV_DATABASE_URL" \
           REDIS_URL="redis://localhost:6379/0" \
           S3_ENDPOINT_URL="http://localhost:9000" \
           uv run python ../scripts/seed_demo.py)
    BASE_URL="http://localhost:8000" \
    SMOKE_USERNAME="demo-operator" \
    SMOKE_PASSWORD="demo-operator-password" \
        bash scripts/smoke.sh
}

step_audit() {
    # --strict по окружению падает на самом проекте (нет на PyPI, editable);
    # аудируем экспорт зависимостей из lock-файла без проекта.
    (cd backend \
        && uv export --frozen --no-emit-project --no-hashes -o /tmp/mgts-audit-requirements.txt \
        && uv run pip-audit --strict -r /tmp/mgts-audit-requirements.txt)
}

run_step "ruff check" step_ruff_check
run_step "ruff format --check" step_ruff_format
run_step "mypy app" step_mypy
run_step "pytest -m unit" step_unit
run_step "infra up (base + dev override)" step_infra
run_step "alembic upgrade head (dev DB)" step_migrate_dev
run_step "pytest -m 'integration or api or contract'" step_integration
run_step "migration roundtrip (test DB: downgrade base + upgrade head)" step_roundtrip
run_step "OpenAPI drift (check_openapi.py)" step_openapi_drift
run_step "TypeScript client drift" step_ts_client
run_step "docker compose build backend" step_docker_build
run_step "smoke (compose up + seed + scripts/smoke.sh)" step_smoke
if [ "$WITH_AUDIT" = "1" ]; then
    run_step "pip-audit --strict" step_audit
fi

echo ""
echo "===================== SUMMARY ====================="
printf '%-6s | %s\n' "RESULT" "STEP"
echo "-------+------------------------------------------"
FAILED=0
for i in "${!STEP_NAMES[@]}"; do
    printf '%-6s | %s\n' "${STEP_RESULTS[$i]}" "${STEP_NAMES[$i]}"
    if [ "${STEP_RESULTS[$i]}" != "PASS" ]; then
        FAILED=$((FAILED + 1))
    fi
done
echo "==================================================="
if [ "$FAILED" -gt 0 ]; then
    echo "ИТОГ: FAIL (${FAILED} шаг(ов) упало)." >&2
    exit 1
fi
echo "ИТОГ: PASS (все ${#STEP_NAMES[@]} шагов)."
