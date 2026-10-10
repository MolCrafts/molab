"""Workspace JSON schema versioning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .fs import FileSystem

MOLAB_SCHEMA_VERSION = 5


def versioned_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap *payload* with the ``schema_version`` envelope FileStore writes."""
    return {"schema_version": MOLAB_SCHEMA_VERSION, **payload}


class IncompatibleSchemaError(RuntimeError):
    """Retained so callers that catch it keep importing.

    Nothing raises it while the format is still moving: during development the
    tree routinely holds files written by an older build, and refusing to open
    a workspace over a version stamp costs more than the mismatch does. Writes
    still stamp the current version, so a file records the build that made it.
    """


def write_versioned_json(
    path: str | Path, payload: dict[str, Any], *, fs: FileSystem | None = None
) -> None:
    """Atomically write *payload* with a ``schema_version`` envelope."""
    versioned = {"schema_version": MOLAB_SCHEMA_VERSION, **payload}
    if fs is not None:
        fs.atomic_write_json(str(path), versioned)
    else:
        from .base import atomic_write_json

        atomic_write_json(Path(path), versioned)


def read_versioned_json(path: str | Path, *, fs: FileSystem | None = None) -> dict[str, Any]:
    """Read a JSON file and return the payload with ``schema_version`` stripped.

    The stamp is dropped, not checked. See :class:`IncompatibleSchemaError`.
    """
    if fs is not None:
        with fs.open(str(path)) as fh:
            data = json.load(fh)
    else:
        with open(path, encoding="utf-8") as fh:  # noqa: PTH123
            data = json.load(fh)
    # No version gate: a stamp that does not match this build is read anyway.
    data.pop("schema_version", None)
    return data
