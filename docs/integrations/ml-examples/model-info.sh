#!/usr/bin/env bash
set -euo pipefail

ML_BASE_URL="${ML_BASE_URL:-http://localhost:8001}"

curl -sS "$ML_BASE_URL/v1/model-info"
