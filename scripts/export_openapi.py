"""Export OpenAPI schema to contracts/openapi/openapi.json.

Run from backend/: uv run python ../scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    from app.main import create_app

    app = create_app()
    schema = app.openapi()
    out = ROOT / "contracts" / "openapi" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    print(f"OpenAPI written: {out} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
