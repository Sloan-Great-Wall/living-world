"""Dump the FastAPI OpenAPI spec to `api-schema/openapi.json`.

Runs without starting the server — FastAPI can emit the schema from the
app object directly. The schema is the cross-layer contract source of
truth (see living_world/web/schemas.py); `make schema` regenerates this
file AND the TypeScript types that the dashboard consumes.

Usage:
    .venv/bin/python scripts/dump_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path

from living_world.web.server import app

OUTPUT = Path(__file__).resolve().parent.parent / "api-schema" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # Quick sanity: how many models + paths did we emit?
    n_paths = len(spec.get("paths", {}))
    n_schemas = len(spec.get("components", {}).get("schemas", {}))
    print(f"wrote {OUTPUT.relative_to(OUTPUT.parent.parent)}  paths={n_paths}  schemas={n_schemas}")


if __name__ == "__main__":
    main()
