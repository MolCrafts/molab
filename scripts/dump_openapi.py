"""Regenerate the checked-in OpenAPI contract from the application factory."""

from __future__ import annotations

import json
from pathlib import Path

from molexp.server.app import create_app


def dump_openapi(target: str | Path) -> Path:
    """Dump the application's OpenAPI schema to *target* and return the path."""
    target = Path(target)
    schema = create_app(serve_static=False).openapi()
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "openapi.json"
    dump_openapi(target)


if __name__ == "__main__":
    main()
