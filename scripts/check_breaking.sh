#!/usr/bin/env bash
# Breaking-change check for the OpenAPI contract using tufin/oasdiff.
#
# Usage:
#   bash scripts/check_breaking.sh [BASE_REF]
#   make breaking-check
#
# Compares contracts/openapi/openapi.json at BASE_REF (default: origin/main)
# against the working-tree contract and reports breaking changes.
#
# Exit codes:
#   0 — no breaking changes (or base contract missing: check skipped)
#   1 — breaking changes detected (oasdiff exit code)
#   2 — docker unavailable (instructions printed)
set -euo pipefail

BASE_REF="${1:-origin/main}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC_DIR="$ROOT/contracts/openapi"
BASE_FILE="/tmp/base-openapi.json"

if [[ ! -f "$SPEC_DIR/openapi.json" ]]; then
  echo "ERROR: $SPEC_DIR/openapi.json not found; run 'make openapi' first." >&2
  exit 1
fi

if ! git -C "$ROOT" show "$BASE_REF:contracts/openapi/openapi.json" > "$BASE_FILE" 2>/dev/null; then
  echo "SKIP: contracts/openapi/openapi.json does not exist at '$BASE_REF' — nothing to compare."
  rm -f "$BASE_FILE"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ERROR: docker is unavailable (not installed or daemon not running).

The breaking-change check runs tufin/oasdiff in a container. Options:
  1. Start docker and re-run:  bash scripts/check_breaking.sh
  2. Run oasdiff directly if installed:
       oasdiff breaking /tmp/base-openapi.json contracts/openapi/openapi.json
  3. Pull the image manually once:  docker pull tufin/oasdiff:latest
EOF
  rm -f "$BASE_FILE"
  exit 2
fi

echo "Comparing OpenAPI contract: $BASE_REF -> working tree (tufin/oasdiff breaking)"
status=0
# label=disable: SELinux hosts (Fedora/RHEL) otherwise deny container reads
# of the bind-mounted files ("permission denied" inside oasdiff).
docker run --rm \
  --security-opt label=disable \
  -v /tmp:/tmp \
  -v "$SPEC_DIR:/spec" \
  tufin/oasdiff:latest breaking --fail-on ERR /tmp/base-openapi.json /spec/openapi.json || status=$?
rm -f "$BASE_FILE"
exit "$status"
