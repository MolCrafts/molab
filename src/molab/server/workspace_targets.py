"""Server-process WorkspaceTarget registry — descriptors for remote
workspace roots.

A :class:`WorkspaceTarget` describes *which remote root to open* — it
exists *before* any workspace is open, so it cannot live on a workspace.
The registry is stored at ``~/.molab/workspace_targets.json`` and
persisted via :func:`molab.workspace.base.atomic_write_json` so a crash
mid-write leaves the previous file intact.

This module sits in ``molab.server`` (Layer 4) and intentionally does
not import ``molab.workflow``.  It reaches downward
into ``molab.workspace`` for two pieces: ``atomic_write_json`` (the
cross-layer atomic-I/O primitive) and the ``FileSystem`` /
``RemoteFileSystem`` types used by
:func:`target_to_filesystem_for_workspace_target`.
"""

from __future__ import annotations

import builtins
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from molab.workspace.base import atomic_write_json
from molab.workspace.fs import FileSystem

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


__all__ = [
    "WorkspaceTarget",
    "WorkspaceTargetRegistry",
    "default_remote_cache_dir",
    "default_workspace_targets_path",
    "target_to_filesystem_for_workspace_target",
]


# Slug-shaped name: ASCII letters / digits / dot / dash / underscore, ≥ 1 char.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class WorkspaceTarget(BaseModel):
    """A semantic root on a molq-owned destination."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    registry_id: str
    cluster_id: str
    root_path: str = Field(min_length=1)
    cache_dir: str | None = None
    cache_mode: Literal["pinned", "strict"] = "pinned"


def default_workspace_targets_path() -> Path:
    """Default on-disk location of the registry — ``~/.molab/workspace_targets.json``."""
    return Path.home() / ".molab" / "workspace_targets.json"


# JSON envelope version — bumps if the on-disk shape ever changes.
#
# Descriptor payloads use the current destination-reference schema.
_STORE_FORMAT_VERSION = 3


class WorkspaceTargetRegistry:
    """Server-process descriptor registry.

    Single-writer assumed (one server process); concurrent server
    processes would race on the JSON file.  In practice ``molab serve``
    is single-process; the assumption holds.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path or default_workspace_targets_path()
        self._cache: dict[str, WorkspaceTarget] | None = None  # lazy load

    @property
    def store_path(self) -> Path:
        return self._store_path

    # ── public surface ────────────────────────────────────────────────

    def list(self) -> builtins.list[WorkspaceTarget]:
        """Return a fresh snapshot in insertion order."""
        return [*self._load().values()]

    def get(self, name: str) -> WorkspaceTarget:
        """Return the named target or raise :class:`KeyError`."""
        cache = self._load()
        if name not in cache:
            raise KeyError(name)
        return cache[name]

    def has(self, name: str) -> bool:
        return name in self._load()

    def add(self, target: WorkspaceTarget) -> WorkspaceTarget:
        """Register a new target; raises :class:`ValueError` if the name is taken."""
        cache = self._load()
        if target.name in cache:
            raise ValueError(f"workspace target {target.name!r} already exists")
        snapshot = dict(cache)
        snapshot[target.name] = target
        self._persist(snapshot)
        # Only mutate the in-memory cache *after* the disk write succeeds.
        self._cache = snapshot
        return target

    def remove(self, name: str) -> None:
        """Remove the named target; raises :class:`KeyError` if absent."""
        cache = self._load()
        if name not in cache:
            raise KeyError(name)
        snapshot = dict(cache)
        del snapshot[name]
        self._persist(snapshot)
        self._cache = snapshot

    # ── internals ─────────────────────────────────────────────────────

    def _load(self) -> dict[str, WorkspaceTarget]:
        if self._cache is not None:
            return self._cache
        if not self._store_path.exists():
            self._cache = {}
            return self._cache
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"corrupt registry at {self._store_path}: {exc}") from exc
        try:
            entries = raw["targets"]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"corrupt registry at {self._store_path}: missing 'targets' list"
            ) from exc

        loaded: dict[str, WorkspaceTarget] = {}
        for entry in entries:
            target = WorkspaceTarget.model_validate(entry)
            loaded[target.name] = target
        self._cache = loaded
        return self._cache

    def _persist(self, snapshot: dict[str, WorkspaceTarget]) -> None:
        payload = {
            "version": _STORE_FORMAT_VERSION,
            "targets": [t.model_dump(mode="json") for t in snapshot.values()],
        }
        atomic_write_json(self._store_path, payload)


def default_remote_cache_dir(target_name: str) -> Path:
    """Resolve the default mirror root for a workspace target."""
    return Path.home() / ".molab" / "remote_cache" / target_name


def target_to_filesystem_for_workspace_target(target: WorkspaceTarget) -> FileSystem:
    """Bind the cache adapter to the explicit registry/cluster/root identity."""
    import hashlib

    from molab.workspace.connection import get_client
    from molab.workspace.fs_cached import CachedRemoteFileSystem
    from molab.workspace.fs_remote import RemoteFileSystem

    client = get_client(target.registry_id)
    inner = RemoteFileSystem(client, target.cluster_id, target.root_path)
    identity = hashlib.sha256(
        f"{target.registry_id}\0{target.cluster_id}\0{target.root_path}".encode()
    ).hexdigest()
    mirror_root = (
        Path(target.cache_dir).expanduser() / identity
        if target.cache_dir
        else default_remote_cache_dir(identity)
    )
    return CachedRemoteFileSystem(inner, mirror_root=mirror_root, cache_mode=target.cache_mode)
