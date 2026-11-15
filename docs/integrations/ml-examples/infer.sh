#!/usr/bin/env bash
set -euo pipefail

ML_BASE_URL="${ML_BASE_URL:-http://localhost:8001}"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

curl -sS -X POST "$ML_BASE_URL/v1/infer" \
  -H 'Content-Type: application/json' \
  --data @"$REPO_ROOT/contracts/ml/examples/request.json"
