"""Detect drift between the committed OpenAPI contract and the live app schema.

Compares contracts/openapi/openapi.json with create_app().openapi() using
normalized JSON (sorted keys). Prints a unified diff summary on drift.

Run from backend/:  uv run python ../scripts/check_openapi.py
(or from repo root: make openapi-check)

Exit codes: 0 — identical; 1 — drift or missing contract file.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

_DIFF_LINES_LIMIT = 80


def _normalize(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _path_summary(committed: dict[str, Any], live: dict[str, Any]) -> list[str]:
    committed_paths = set(committed.get("paths", {}))
    live_paths = set(live.get("paths", {}))
    lines: list[str] = []
    for path in sorted(committed_paths - live_paths):
        lines.append(f"  removed path: {path}")
    for path in sorted(live_paths - committed_paths):
        lines.append(f"  added path:   {path}")
    for path in sorted(committed_paths & live_paths):
        committed_methods = set(committed["paths"][path])
        live_methods = set(live["paths"][path])
        for method in sorted(committed_methods - live_methods):
            lines.append(f"  removed operation: {method.upper()} {path}")
        for method in sorted(live_methods - committed_methods):
            lines.append(f"  added operation:   {method.upper()} {path}")
    return lines


def main() -> int:
    from app.main import create_app

    committed_path = ROOT / "contracts" / "openapi" / "openapi.json"
    if not committed_path.exists():
        print(f"ERROR: committed contract not found: {committed_path}", file=sys.stderr)
        print("Run `make openapi` to export it first.", file=sys.stderr)
        return 1

    committed = json.loads(committed_path.read_text(encoding="utf-8"))
    live = create_app().openapi()

    committed_text = _normalize(committed)
    live_text = _normalize(live)
    if committed_text == live_text:
        print(f"OK: committed OpenAPI matches the live app ({len(live['paths'])} paths)")
        return 0

    diff = list(
        difflib.unified_diff(
            committed_text.splitlines(),
            live_text.splitlines(),
            fromfile="contracts/openapi/openapi.json (committed)",
            tofile="app.openapi() (live)",
            lineterm="",
            n=1,
        )
    )
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    print("DRIFT: committed OpenAPI differs from the live app schema.", file=sys.stderr)
    print(f"Diff: +{added}/-{removed} lines.", file=sys.stderr)
    summary = _path_summary(committed, live)
    if summary:
        print("Path/operation changes:", file=sys.stderr)
        print("\n".join(summary), file=sys.stderr)
    print(f"Unified diff (first {_DIFF_LINES_LIMIT} lines):", file=sys.stderr)
    print("\n".join(diff[:_DIFF_LINES_LIMIT]), file=sys.stderr)
    if len(diff) > _DIFF_LINES_LIMIT:
        print(f"... {len(diff) - _DIFF_LINES_LIMIT} more diff lines", file=sys.stderr)
    print(
        "Fix: cd backend && uv run python ../scripts/export_openapi.py (make openapi)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
