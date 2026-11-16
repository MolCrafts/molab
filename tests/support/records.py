"""Read and write a Folder's ``index.md`` record in tests.

The record is the YAML frontmatter of ``<dir>/index.md`` (D88): the canonical
zone, plus the derived ``index:`` block (D89). These helpers keep tests from
re-implementing the split.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from molab import frontmatter


def record_path(directory: str | os.PathLike[str]) -> Path:
    return Path(str(directory)) / "index.md"


def _head(directory: str | os.PathLike[str]) -> tuple[dict[str, Any], str]:
    return frontmatter.split(record_path(directory).read_text(encoding="utf-8"))


def read_record(directory: str | os.PathLike[str]) -> dict[str, Any]:
    """The canonical zone of *directory*'s record (no ``index:`` block)."""
    meta, _body = _head(directory)
    return {key: value for key, value in meta.items() if key != "index"}


def read_index_block(directory: str | os.PathLike[str]) -> dict[str, Any]:
    """The derived ``index:`` block of *directory*'s record."""
    meta, _body = _head(directory)
    block = meta.get("index")
    return dict(block) if isinstance(block, dict) else {}


def write_record(
    directory: str | os.PathLike[str],
    canonical: dict[str, Any],
    *,
    index: dict[str, Any] | None = None,
    body: str | None = None,
) -> Path:
    """Write *canonical* (and optionally *index* / *body*) as *directory*'s record.

    An omitted *index* or *body* keeps what the file already holds.
    """
    path = record_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    old_index: dict[str, Any] = {}
    old_body = ""
    if path.is_file():
        meta, old_body = _head(directory)
        raw = meta.get("index")
        old_index = dict(raw) if isinstance(raw, dict) else {}
    meta_out: dict[str, Any] = dict(canonical)
    block = old_index if index is None else index
    if block:
        meta_out["index"] = block
    path.write_text(
        frontmatter.dump(meta_out, old_body if body is None else body), encoding="utf-8"
    )
    return path


def update_record(directory: str | os.PathLike[str], **fields: Any) -> dict[str, Any]:
    """Merge *fields* into *directory*'s canonical zone; return the new zone."""
    canonical = read_record(directory)
    canonical.update(fields)
    write_record(directory, canonical)
    return canonical
