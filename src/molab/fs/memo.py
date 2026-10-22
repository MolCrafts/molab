"""``StatMemo`` — a stat-validated, in-process read memo over a ``FileSystem``.

Why it exists
=============
Reading a workspace is dominated by re-reading the same small files: a Run's
``_ops/run.json`` is consulted by ``status`` / ``finished_at`` /
``execution_history`` / ``is_retryable`` and each of those used to be an
``exists`` + ``open`` + ``json.load`` + pydantic validate.  On a network
filesystem every one of those is a metadata round-trip; over SSH each is a
full round-trip.

``StatMemo`` turns a repeated read into **one ``stat``**: a memoized value is
served when the file's ``(size, mtime)`` is unchanged, re-loaded otherwise.
Through :class:`~molab.workspace.fs_cached.CachedRemoteFileSystem` a ``stat``
of a pinned entry is a local index lookup, so the same policy is free on a
remote workspace — no separate "pin" mode is needed.

Law check (CLAUDE.md "One source of truth"): nothing here is persisted.  The
memo is a cache *of* the authoritative file, validated against that file's
stat on every read and dropped by the writers on the same instance
(:meth:`invalidate`).  It is never consulted as truth on its own.

Semantics
=========
* ``fetch``/``get``: stat **before** load.  If the file changes between the
  stat and the load, the stored key is the *older* one, so the next call
  re-stats, sees a different key, and reloads — never a stale hit.  (The
  other order — load then stat — could pin new stat + old content forever.)
* Absence is never memoized: a missing file raises ``FileNotFoundError`` /
  ``NotADirectoryError`` (``get_or_none`` maps both to ``None``).
* A loader that raises stores nothing.
* ``slot`` keys several parsed forms of the same file (e.g. the raw dict and a
  typed model) — :meth:`invalidate` drops every slot of a path.

Residual risk (documented, accepted): two rewrites of a file to the **same
size** inside one mtime tick are invisible to *readers* until the file changes
again.  Local ext4/xfs have nanosecond mtimes; the SSH transport's ``stat``
reports whole seconds.  Writers are unaffected — a read-modify-write reads
fresh under its lock (see ``Folder.update_ops_json``).

Thread-safety: dict item get/set are atomic under the GIL; a concurrent
double-load stores the same value twice.  No lock is taken on the read path.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .base import FileSystem, PathArg, StatResult

__all__ = ["MemoKey", "StatMemo"]

#: The change-detection key of a file: ``(size, mtime)`` from ``fs.stat``.
MemoKey = tuple[int, float]

_MISSING: tuple[type[OSError], ...] = (FileNotFoundError, NotADirectoryError)


class StatMemo:
    """Per-``FileSystem`` memo of parsed file contents, validated by ``stat``."""

    def __init__(self, fs: FileSystem) -> None:
        self._fs = fs
        self._entries: dict[tuple[str, str], tuple[MemoKey, object]] = {}

    # ── keys ──────────────────────────────────────────────────────────────

    @staticmethod
    def key_of(st: StatResult) -> MemoKey:
        return (st.size, st.mtime)

    # ── reads ─────────────────────────────────────────────────────────────

    def fetch[T](
        self, path: PathArg, load: Callable[[str], T], *, slot: str = ""
    ) -> tuple[T, bool]:
        """Return ``(value, hit)``; one ``stat`` on a hit, ``stat`` + *load* otherwise.

        Raises ``FileNotFoundError`` / ``NotADirectoryError`` when *path* is
        absent (never memoized); any exception *load* raises propagates and
        nothing is stored.
        """
        p = os.fspath(path)
        key = self.key_of(self._fs.stat(p))
        hit = self._entries.get((p, slot))
        if hit is not None and hit[0] == key:
            return cast("T", hit[1]), True
        value = load(p)
        self._entries[(p, slot)] = (key, value)
        return value, False

    def get[T](self, path: PathArg, load: Callable[[str], T], *, slot: str = "") -> T:
        return self.fetch(path, load, slot=slot)[0]

    def fetch_or_none[T](
        self, path: PathArg, load: Callable[[str], T], *, slot: str = ""
    ) -> tuple[T | None, bool]:
        """:meth:`fetch` that maps an absent *path* to ``(None, False)``."""
        try:
            return self.fetch(path, load, slot=slot)
        except _MISSING:
            return None, False

    def get_or_none[T](
        self, path: PathArg, load: Callable[[str], T], *, slot: str = ""
    ) -> T | None:
        return self.fetch_or_none(path, load, slot=slot)[0]

    def is_fresh(self, path: PathArg, *, slot: str = "") -> bool:
        """``True`` iff a memoized value exists and matches the file's current stat.

        One ``stat``; ``False`` (never raises) when *path* is absent.
        """
        p = os.fspath(path)
        hit = self._entries.get((p, slot))
        if hit is None:
            return False
        try:
            return hit[0] == self.key_of(self._fs.stat(p))
        except _MISSING:
            return False

    # ── writes ────────────────────────────────────────────────────────────

    def put(self, path: PathArg, value: object, st: StatResult, *, slot: str = "") -> None:
        """Seed *value* for *path* under the stat *st* taken **before** it was read."""
        self._entries[(os.fspath(path), slot)] = (self.key_of(st), value)

    def invalidate(self, path: PathArg | None = None) -> None:
        """Drop every slot of *path* (or everything when *path* is ``None``)."""
        if path is None:
            self._entries.clear()
            return
        p = os.fspath(path)
        for k in [k for k in self._entries if k[0] == p]:
            self._entries.pop(k, None)

    def __len__(self) -> int:
        return len(self._entries)
