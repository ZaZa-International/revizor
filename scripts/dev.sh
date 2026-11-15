#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> Создан .env из .env.example."
fi

exec docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
