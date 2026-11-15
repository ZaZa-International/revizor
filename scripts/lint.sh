#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"

echo "==> ruff check..."
uv run ruff check .

echo "==> ruff format --check..."
uv run ruff format --check .

echo "==> mypy..."
uv run mypy app

echo "==> Все проверки пройдены."
