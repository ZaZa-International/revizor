#!/usr/bin/env bash
# Generate the TypeScript schema (schema.d.ts) from the committed OpenAPI contract.
#
# Usage:
#   bash scripts/generate_ts_client.sh
#   make ts-client
#
# Output: contracts/typescript/schema.d.ts (openapi-typescript).
# Usage with openapi-fetch: see contracts/typescript/README.md.
# Requires: Node.js + npx (network access on first run to fetch openapi-typescript).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f contracts/openapi/openapi.json ]]; then
  echo "ERROR: contracts/openapi/openapi.json not found; run 'make openapi' first." >&2
  exit 1
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "ERROR: npx not found — install Node.js (>=18) to generate the TS client." >&2
  exit 1
fi

mkdir -p contracts/typescript
npx --yes openapi-typescript@latest contracts/openapi/openapi.json -o contracts/typescript/schema.d.ts
echo "Generated contracts/typescript/schema.d.ts"
echo "Usage: see contracts/typescript/README.md (openapi-fetch example)."
