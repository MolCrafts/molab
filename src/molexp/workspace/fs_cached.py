"""Caching :class:`FileSystem` decorator — lazy-download mirror for
remote workspaces.

Wraps an inner :class:`~molexp.workspace.fs.FileSystem` (only meaningful
for :class:`~molexp.workspace.fs_remote.RemoteFileSystem`) and maintains
a server-side mirror under ``<mirror_root>/files/...``.

**Pin-until-refresh policy** (default): once a path is in the local
index/mirror it is trusted forever.  Age / ``ttl_seconds`` does **not**
trigger automatic revalidation — the operator refreshes via
``POST /api/workspace/cache/refresh`` (or ``invalidate``).  Cache misses
still go to the remote FS and populate the mirror.

``ttl_seconds=0`` is an opt-in strict mode: every read re-stats the remote
and reuses mirror bytes only when mtime/size still match.

Index files are not special-cased — they are just paths.  The eager
prefetch helper :func:`prefetch_workspace_indices` walks the workspace by
``listdir`` plus the per-entity ``workspace.json`` / ``project.json`` /
``experiment.json`` / ``run.json`` metadata files through
:meth:`read_text`, so the navigation tree is populated as a side-effect
of caching.  The entity ``*.json`` is the sole truth source; there is no
separate plural container-index chain.

Layer rule: lives in the workspace layer next to ``fs_local.py`` and
``fs_remote.py``; reaches only into sibling FS modules and the
:func:`atomic_write_json` primitive.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from .fs import DirEntry, FileSystem, PathArg, StatResult
from .fs_local import LocalFileSystem

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .workspace import Workspace

__all__ = [
    "INDEX_FILE_NAMES",
    "CachedRemoteFileSystem",
    "PrefetchWarning",
    "prefetch_workspace_indices",
]


# Outside-in parallel prefetch: concurrent SSH ops per level. Override with
# ``MOLEXP_PREFETCH_WORKERS`` (1 = serial, useful in tests).
_DEFAULT_PREFETCH_WORKERS = 8

logger = logging.getLogger(__name__)

INDEX_FILE_NAMES: frozenset[str] = frozenset(
    {
        "workspace.json",
        "project.json",
        "experiment.json",
        "run.json",
    }
)
"""Files whose basename identifies them as a navigation-index artefact.

In molexp's workspace layout these singular names are an entity's own
metadata (``<child>/run.json`` etc.); the entity ``*.json`` is the sole
truth source for the navigation tree.  Their basenames double as the
``scope="indices"`` invalidation set, so a refresh drops cached
navigation metadata while sparing log/asset bytes.
"""

NAVIGATION_FILE_NAMES: frozenset[str] = frozenset(
    INDEX_FILE_NAMES | {"assets.json", "meta.yaml", "metadata.json"}
)
"""Basenames whose mirrored bytes are never evicted to make room.

These are what the navigation tree is *made of*; evicting them to cache a
log tail would trade a 0-round-trip tree for a re-fetch of every node. The
run ops sidecar (``_ops/run.json``) is navigation too but shares its
basename with the run entity file, so it is matched by path suffix instead.
"""

_OPS_SUFFIX = "/_ops/run.json"

_SIDECAR_FILENAME = "_index.json"
# v2: ``dirs`` holds typed DirEntry rows (not bare names) so a cached listing
# also answers stat/is_dir for its children. A v1 sidecar is simply ignored —
# this is a cache, and re-walking costs one prefetch.
_SIDECAR_VERSION = 2

_DEFAULT_MIRROR_MAX_FILE_BYTES = 64 * 1024 * 1024
_DEFAULT_MIRROR_BUDGET_BYTES = 4 * 1024 * 1024 * 1024
_SIDECAR_DEBOUNCE_SECONDS = 1.0


@dataclass(frozen=True)
class _Entry:
    """One cached file/dir/missing record.

    ``mirrored`` tracks whether the bytes are on local disk: an evicted file
    keeps its entry (so ``stat``/``exists``/``is_dir`` still answer with zero
    round-trips) and only loses its mirror copy.
    """

    size: int
    mtime: float
    fetched_at: float
    kind: str  # "file" | "dir" | "missing"
    mirrored: bool = False
    last_used: float = 0.0


@dataclass(frozen=True)
class _DirListing:
    """One cached directory listing, with per-entry type and metadata."""

    entries: tuple[DirEntry, ...]
    fetched_at: float

    @property
    def names(self) -> tuple[str, ...]:
        """Entry names — the shape the pre-scandir cache exposed."""
        return tuple(e.name for e in self.entries)


def _is_navigation(key: str) -> bool:
    """Whether *key* holds navigation metadata (never evicted from the mirror)."""
    return key.rsplit("/", 1)[-1] in NAVIGATION_FILE_NAMES or key.endswith(_OPS_SUFFIX)


@dataclass(frozen=True)
class PrefetchWarning:
    """One node that failed during :func:`prefetch_workspace_indices`."""

    path: str
    reason: str


class CachedRemoteFileSystem:
    """Lazy-download mirror over any :class:`FileSystem`.

    **Default (``ttl_seconds > 0``)**: pin-until-refresh.  Any path present
    in the sidecar/mirror is served locally with **zero** remote I/O until
    the operator invalidates/refreshes.  Mutations still go to the inner
    FS and invalidate the affected entry.

    **Strict (``ttl_seconds == 0``)**: every read re-stats the remote and
    reuses mirror bytes only when mtime/size match (no silent pin).

    The mirror layout reflects the remote path verbatim (leading ``/``
    stripped) under ``<mirror_root>/files/``, so a remote path
    ``/home/me/run/log.txt`` ends up at ``<mirror_root>/files/home/me/
    run/log.txt``.  This stays debuggable and lets ``find`` walk the
    mirror.

    Args:
        inner: The :class:`FileSystem` to cache.
        mirror_root: Local directory holding the mirror.  Created on
            first write.
        ttl_seconds: ``>0`` (default) = pin-until-refresh.  ``0`` =
            revalidate via remote ``stat`` on every read.
        revalidate_before: Entries cached before this wall-clock time are
            revalidated **once** on next use, then re-pinned.  A CLI process
            passes ``time.time()`` so a single invocation sees fresh data
            without giving up pinning for the rest of its run.
        mirror_max_file_bytes: Files larger than this are returned to the
            caller but never written to the mirror — a multi-GB artifact
            previewed once must not be copied whole and pinned forever.
        mirror_budget_bytes: Total mirrored bytes allowed; exceeding it
            evicts least-recently-used non-navigation files.
    """

    def __init__(
        self,
        inner: FileSystem,
        *,
        mirror_root: Path | str,
        ttl_seconds: int = 300,
        revalidate_before: float | None = None,
        mirror_max_file_bytes: int = _DEFAULT_MIRROR_MAX_FILE_BYTES,
        mirror_budget_bytes: int = _DEFAULT_MIRROR_BUDGET_BYTES,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self._inner = inner
        self._local = LocalFileSystem()
        self._mirror_root = Path(mirror_root)
        self._files_root = self._mirror_root / "files"
        self._ttl_seconds = ttl_seconds
        self._revalidate_before = revalidate_before
        self._mirror_max_file_bytes = mirror_max_file_bytes
        self._mirror_budget_bytes = mirror_budget_bytes
        self._mirrored_bytes = 0
        self._index: dict[str, _Entry] = {}
        self._dir_index: dict[str, _DirListing] = {}
        self._sidecar = self._mirror_root / _SIDECAR_FILENAME
        # Sidecar write batching: while ``_defer_persist`` is set (inside
        # ``batched()``), per-op writes only mark ``_sidecar_dirty`` and the
        # full serialization happens once on batch exit — turning a bulk walk
        # (e.g. ``prefetch_workspace_indices``) from O(records²) into O(records).
        self._defer_persist = False
        self._sidecar_dirty = False
        # Outside batched(), writes are debounced to at most one per second:
        # a walk that records 1000 entries rewrites the sidecar a handful of
        # times instead of 1000, which is what made it O(records²) in bytes.
        self._sidecar_timer: threading.Timer | None = None
        self._sidecar_last_write = 0.0
        self._atexit_registered = False
        # Lifecycle flags — a brand-new remote root has no sidecar; that is
        # normal. ``connect`` / ``index`` (or ``prepare``) flip these once
        # the local mirror is ready and navigation metadata is warm.
        self._connected = False
        self._indexed = False
        self._remote_root: str | None = None
        self._lock = threading.RLock()
        self._index_thread: threading.Thread | None = None
        self._indexing = False
        # Per-thread: active refresh bypasses pin and re-fetches from remote.
        # UI threads keep serving the pinned mirror while a refresh runs.
        self._tls = threading.local()
        # Always own the local mirror tree up-front so a missing
        # ``_index.json`` never surfaces as "Path not found" on first write.
        self._ensure_mirror_dirs()
        self._load_sidecar()
        self._mirrored_bytes = sum(e.size for e in self._index.values() if e.mirrored)
        atexit.register(self.flush)
        if self._index or self._dir_index:
            # Survived a previous session — treat as already indexed until
            # the caller re-runs ``index()`` / invalidates.
            self._indexed = True

    # ── Test-only introspection ─────────────────────────────────────────

    @property
    def inner(self) -> FileSystem:
        return self._inner

    @property
    def mirror_root(self) -> Path:
        return self._mirror_root

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    @property
    def connected(self) -> bool:
        """True after a successful :meth:`connect` (remote root reachable)."""
        return self._connected

    @property
    def indexed(self) -> bool:
        """True after :meth:`index` / :meth:`connect_and_index` (or a loaded sidecar)."""
        return self._indexed

    @property
    def ready(self) -> bool:
        """True when navigation can be served from the local mirror/index.

        SSH may still be deferred (warm reopen) — :attr:`connected` is the
        probe flag; :attr:`ready` is "UI can load the tree".
        """
        return self._indexed

    @property
    def indexing(self) -> bool:
        """True while a background :meth:`schedule_index` walk is in flight."""
        return self._indexing

    def cached_paths(self) -> list[str]:
        """Snapshot of cached file/dir/missing paths — handy in tests."""
        return list(self._index.keys())

    # ── Connect / index lifecycle ───────────────────────────────────────

    def _ensure_mirror_dirs(self) -> None:
        """Create ``mirror_root/`` and ``mirror_root/files/`` if missing."""
        self._mirror_root.mkdir(parents=True, exist_ok=True)
        self._files_root.mkdir(parents=True, exist_ok=True)

    def _ensure_connected(self) -> None:
        """Open SSH on first cache miss (warm reopen defers the probe).

        When neither :meth:`prepare` nor :meth:`connect` has recorded a root
        (unit tests / direct use), skip the probe and let the inner FS answer.
        """
        if self._connected:
            return
        root = self._remote_root
        if root is None:
            return
        self.connect(root)

    def connect(self, root: str) -> None:
        """Probe the remote root and materialise an empty local index if needed.

        A first-time workspace has no ``_index.json`` — that is expected.
        We create the local mirror dirs and write an empty sidecar so later
        cache records never fail with "No such file or directory" on the
        sidecar rename. Re-entrant / idempotent.
        """
        self._remote_root = root
        self._ensure_mirror_dirs()
        try:
            reachable = self._inner.exists(root) or self._inner.is_dir(root)
        except Exception as exc:
            self._connected = False
            raise ConnectionError(f"remote root unreachable: {root}: {exc}") from exc
        if not reachable:
            self._connected = False
            raise FileNotFoundError(f"remote root not found: {root}")
        # Missing sidecar is normal — write current in-memory state (often empty).
        if not self._sidecar.exists():
            self._write_sidecar()
        self._connected = True

    @contextlib.contextmanager
    def force_fetch(self) -> Iterator[None]:
        """Bypass pin for this thread — every read/listdir hits the remote.

        Used by active refreshes. Concurrent UI threads keep serving the
        pinned mirror (their ``_tls.force_fetch`` stays false).
        """
        prev = getattr(self._tls, "force_fetch", False)
        self._tls.force_fetch = True
        try:
            yield
        finally:
            self._tls.force_fetch = prev

    def index(self, workspace: Workspace) -> list[PrefetchWarning]:
        """Actively refresh navigation metadata from remote (blocking).

        Always force-fetches (does not trust pin). Outside-in parallel walk
        via :func:`prefetch_workspace_indices`. Sets :attr:`indexed`.
        """
        self._remote_root = str(workspace.root)
        if not self._connected:
            self.connect(str(workspace.root))
        with self.force_fetch():
            warnings = prefetch_workspace_indices(workspace)
        # Prefetch uses batched(); flush guarantees the sidecar is on disk.
        self.flush()
        if not self._sidecar.exists():
            self._write_sidecar()
        self._indexed = True
        self._indexing = False
        return warnings

    def schedule_refresh(self, workspace: Workspace) -> None:
        """Run :meth:`index` on a daemon thread (non-blocking active refresh).

        Idempotent while a walk is already in flight. Failures are logged;
        the operator can retry via ``POST /api/workspace/cache/refresh``.
        """
        with self._lock:
            if self._indexing:
                return
            if self._index_thread is not None and self._index_thread.is_alive():
                return
            self._indexing = True
            root = str(workspace.root)
            self._remote_root = root

            def _run() -> None:
                try:
                    self.index(workspace)
                except Exception:
                    logger.exception(
                        "background remote index failed for %s — use cache/refresh",
                        root,
                    )
                    self._indexing = False

            self._index_thread = threading.Thread(
                target=_run,
                name="molexp-remote-index",
                daemon=True,
            )
            self._index_thread.start()

    # Back-compat alias
    schedule_index = schedule_refresh

    def prepare(
        self,
        workspace: Workspace,
        *,
        block_index: bool = False,
        refresh_on_open: bool = True,
    ) -> list[PrefetchWarning]:
        """Open path for ``molexp serve`` / API.

        * **Always** serves from the local pin immediately when present
          (no TTL auto-expiry; no silent revalidation on read).
        * **On open** (``refresh_on_open=True``, default): fire **one**
          active refresh — async outside-in parallel walk that force-
          fetches from remote and updates the pin.  Not age-based; only
          this open trigger (or the user Refresh button) re-pulls.
        * **Cold** (no index yet): probe SSH, then same async/blocking
          refresh so the tree fills in.
        """
        self._remote_root = str(workspace.root)
        if self._indexed:
            # Warm: UI can read local pin now; optionally kick one active refresh.
            if refresh_on_open:
                if block_index:
                    return self.index(workspace)
                self.schedule_refresh(workspace)
            return []
        # Cold — must connect before any remote walk.
        self.connect(str(workspace.root))
        if block_index:
            return self.index(workspace)
        if refresh_on_open:
            self.schedule_refresh(workspace)
        return []

    def connect_and_index(self, workspace: Workspace) -> list[PrefetchWarning]:
        """Connect + build index synchronously (blocking). Prefer :meth:`prepare`."""
        return self.prepare(workspace, block_index=True, refresh_on_open=True)

    # ── Path operations (always delegate; no I/O) ───────────────────────

    def join(self, *parts: PathArg) -> str:
        return self._inner.join(*parts)

    def dirname(self, path: PathArg) -> str:
        return self._inner.dirname(path)

    def basename(self, path: PathArg) -> str:
        return self._inner.basename(path)

    def resolve(self, path: PathArg) -> str:
        return self._inner.resolve(path)

    def is_absolute(self, path: PathArg) -> bool:
        return self._inner.is_absolute(path)

    # ── Existence / type ────────────────────────────────────────────────

    def exists(self, path: PathArg) -> bool:
        key = self.resolve(path)
        entry = self._pinned_entry(key)
        if entry is not None:
            return entry.kind != "missing"
        self._ensure_connected()
        result = self._inner.exists(key)
        if not result:
            # Negative cache: future ``exists`` returns False without SSH.
            self._record(key, kind="missing", size=0, mtime=0.0)
        return result

    def is_dir(self, path: PathArg) -> bool:
        key = self.resolve(path)
        entry = self._pinned_entry(key)
        if entry is not None:
            return entry.kind == "dir"
        self._ensure_connected()
        result = self._inner.is_dir(key)
        if result:
            self._record(key, kind="dir", size=0, mtime=time.time())
        return result

    def is_file(self, path: PathArg) -> bool:
        key = self.resolve(path)
        entry = self._pinned_entry(key)
        if entry is not None:
            return entry.kind == "file"
        self._ensure_connected()
        result = self._inner.is_file(key)
        if result:
            # Don't fetch yet — just record what we learned.
            stat_value = self._safe_stat(key)
            if stat_value is not None:
                self._record(
                    key,
                    kind="file",
                    size=stat_value.size,
                    mtime=stat_value.mtime,
                )
        return result

    # ── Directory operations ────────────────────────────────────────────

    def mkdir(self, path: PathArg, *, parents: bool = True, exist_ok: bool = True) -> None:
        key = self.resolve(path)
        self._inner.mkdir(key, parents=parents, exist_ok=exist_ok)
        self._record(key, kind="dir", size=0, mtime=time.time())
        self._invalidate_dir(self._inner.dirname(key))

    def listdir(self, path: PathArg) -> list[str]:
        # Names come from the typed listing, so one round-trip also answers
        # stat/is_dir/exists for every child (see ``scandir``).
        return [entry.name for entry in self.scandir(path, with_stat=True)]

    def glob(self, path: PathArg, pattern: str) -> Iterable[str]:
        # Glob is intentionally uncached — patterns are open-ended and
        # caching them risks staleness on every directory change.
        return self._inner.glob(path, pattern)

    def rglob(self, path: PathArg, pattern: str) -> Iterable[str]:
        return self._inner.rglob(path, pattern)

    def scandir(self, path: PathArg, *, with_stat: bool = True) -> list[DirEntry]:  # noqa: ARG002 — remote listings carry metadata for free
        """List a directory, pinning the listing **and** every child entry.

        This is the round-trip multiplier that matters on a remote workspace:
        one ``scandir`` of ``runs/`` answers the later ``stat`` / ``is_dir`` /
        ``exists`` / ``is_file`` of every run directory beneath it for free,
        instead of one SSH round-trip apiece.

        ``with_stat`` is ignored for the same reason the remote FS ignores it:
        the listing carries size and mtime whether or not we ask.
        """
        key = self.resolve(path)
        cached = self._pinned_dir(key)
        if cached is not None:
            return list(cached.entries)
        self._ensure_connected()
        entries = tuple(self._inner.scandir(key, with_stat=True))
        now = time.time()
        with self._lock:
            self._dir_index[key] = _DirListing(entries=entries, fetched_at=now)
            self._record_children(key, entries, now)
            self._persist_sidecar()
        return list(entries)

    def read_range(self, path: PathArg, offset: int, length: int) -> bytes:
        """Read a byte window, serving it from the mirror when we already have it.

        A range is never *itself* mirrored: writing a slice of a multi-GB
        artifact under that path's key would poison the cache with a partial
        file that later reads would trust as whole.
        """
        key = self.resolve(path)
        mirror_path = self._mirror_for(key)
        entry = self._pinned_entry(key)
        if (
            entry is not None
            and entry.kind == "file"
            and entry.mirrored
            and self._local.exists(mirror_path)
        ):
            self._touch_entry(key)
            return self._local.read_range(mirror_path, offset, length)
        self._ensure_connected()
        return self._inner.read_range(key, offset, length)

    # ── Read ────────────────────────────────────────────────────────────

    def read_text(self, path: PathArg, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding)

    def read_bytes(self, path: PathArg) -> bytes:
        key = self.resolve(path)
        mirror_path = self._mirror_for(key)
        entry = self._pinned_entry(key)
        if entry is not None and entry.kind == "file" and self._local.exists(mirror_path):
            self._touch_entry(key)
            return self._local.read_bytes(mirror_path)
        if entry is not None and entry.kind == "missing":
            raise FileNotFoundError(key)
        # Strict mode (ttl=0): revalidate via stat; serve mirror if unchanged.
        known = self._index.get(key)
        if (
            self._ttl_seconds == 0
            and known is not None
            and known.kind == "file"
            and self._local.exists(mirror_path)
        ):
            self._ensure_connected()
            if self._revalidate_file_entry(key, known):
                return self._local.read_bytes(mirror_path)
        # Miss (or strict revalidation failed) — fetch from remote.
        self._ensure_connected()
        try:
            data = self._inner.read_bytes(key)
        except FileNotFoundError:
            self._record(key, kind="missing", size=0, mtime=0.0)
            raise
        # A ``scandir`` of the parent already told us size+mtime; re-stating
        # here would double the round-trips of every cold read.
        if known is not None and known.kind == "file":
            size, mtime = known.size, known.mtime
        else:
            stat_value = self._safe_stat(key)
            size = len(data) if stat_value is None else stat_value.size
            mtime = time.time() if stat_value is None else stat_value.mtime
        mirrored = self._maybe_write_mirror(key, mirror_path, data)
        self._record(key, kind="file", size=size, mtime=mtime, mirrored=mirrored)
        return data

    def open(self, path: PathArg, mode: str = "r", encoding: str = "utf-8") -> IO[Any]:  # noqa: ARG002 — `mode` kept to mirror RemoteFileSystem.open's signature
        # Mirror RemoteFileSystem's behaviour: read-only string buffer.
        import io

        return io.StringIO(self.read_text(path, encoding=encoding))

    # ── Write ───────────────────────────────────────────────────────────

    def write_text(self, path: PathArg, content: str, *, mode: int = 0o600) -> None:
        key = self.resolve(path)
        self._invalidate(key)
        self._inner.write_text(key, content, mode=mode)

    def write_bytes(self, path: PathArg, content: bytes, *, mode: int = 0o600) -> None:
        key = self.resolve(path)
        self._invalidate(key)
        self._inner.write_bytes(key, content, mode=mode)

    # ── Mutations ───────────────────────────────────────────────────────

    def rename(self, src: PathArg, dst: PathArg) -> None:
        src_key = self.resolve(src)
        dst_key = self.resolve(dst)
        self._invalidate(src_key)
        self._invalidate(dst_key)
        self._inner.rename(src_key, dst_key)

    def remove(self, path: PathArg, *, recursive: bool = False) -> None:
        key = self.resolve(path)
        self._invalidate(key, recursive=recursive)
        self._inner.remove(key, recursive=recursive)

    def copy(self, src: PathArg, dst: PathArg) -> None:
        dst_key = self.resolve(dst)
        self._invalidate(dst_key)
        self._inner.copy(src, dst_key)

    def copytree(self, src: PathArg, dst: PathArg, *, dirs_exist_ok: bool = False) -> None:
        dst_key = self.resolve(dst)
        self._invalidate(dst_key, recursive=True)
        self._inner.copytree(src, dst_key, dirs_exist_ok=dirs_exist_ok)

    # ── Metadata ────────────────────────────────────────────────────────

    def stat(self, path: PathArg) -> StatResult:
        key = self.resolve(path)
        entry = self._pinned_entry(key)
        if entry is not None and entry.kind != "missing":
            return StatResult(
                size=entry.size,
                mtime=entry.mtime,
                is_dir=entry.kind == "dir",
                is_file=entry.kind == "file",
            )
        self._ensure_connected()
        result = self._inner.stat(key)
        kind = "dir" if result.is_dir else "file" if result.is_file else "missing"
        self._record(key, kind=kind, size=result.size, mtime=result.mtime)
        return result

    def lstat(self, path: PathArg) -> StatResult:
        return self.stat(path)

    def touch(self, path: PathArg) -> None:
        key = self.resolve(path)
        self._invalidate(key)
        self._inner.touch(key)

    def chmod(self, path: PathArg, mode: int) -> None:
        self._inner.chmod(path, mode)

    def getsize(self, path: PathArg) -> int:
        return self.stat(path).size

    # ── Symlinks ────────────────────────────────────────────────────────

    def symlink(self, src: PathArg, dst: PathArg) -> None:
        dst_key = self.resolve(dst)
        self._invalidate(dst_key)
        self._inner.symlink(src, dst_key)

    # ── Atomic I/O ──────────────────────────────────────────────────────

    def atomic_write_json(self, path: PathArg, data: object) -> None:
        key = self.resolve(path)
        self._invalidate(key)
        self._inner.atomic_write_json(key, data)

    def atomic_write_text(self, path: PathArg, content: str, *, encoding: str = "utf-8") -> None:
        key = self.resolve(path)
        self._invalidate(key)
        self._inner.atomic_write_text(key, content, encoding=encoding)

    # ── Bulk population (one round-trip in, many entries out) ───────────

    def absorb_listings(self, listings: dict[str, list[DirEntry]]) -> None:
        """Populate the cache from a bulk directory walk.

        Records every listing **and** every child entry, so the whole
        navigation tree answers ``listdir`` / ``stat`` / ``is_dir`` / ``exists``
        with zero remote calls after a single ``walk_entries``.
        """
        now = time.time()
        with self._lock, self.batched():
            for directory, entries in listings.items():
                rows = tuple(entries)
                self._dir_index[directory] = _DirListing(entries=rows, fetched_at=now)
                self._record_children(directory, rows, now)
            self._persist_sidecar()

    def absorb_files(self, files: dict[str, bytes]) -> None:
        """Mirror bytes fetched in bulk, honouring the per-file size cap."""
        with self.batched():
            for key, data in files.items():
                if len(data) > self._mirror_max_file_bytes:
                    continue
                mirror_path = self._mirror_for(key)
                self._write_mirror(mirror_path, data)
                known = self._index.get(key)
                mtime = known.mtime if known is not None else time.time()
                size = known.size if known is not None else len(data)
                self._record(key, kind="file", size=size, mtime=mtime, mirrored=True)

    def _record_children(self, directory: str, entries: tuple[DirEntry, ...], now: float) -> None:
        """Record one listing's children. Caller must hold ``_lock``."""
        for entry in entries:
            child = self._inner.join(directory, entry.name)
            known = self._index.get(child)
            if known is not None and known.kind == "file" and known.mirrored:
                continue
            kind = "dir" if entry.is_dir else "file" if entry.is_file else "missing"
            self._index[child] = _Entry(
                size=entry.size,
                mtime=entry.mtime,
                fetched_at=now,
                kind=kind,
            )

    # ── Cache control ───────────────────────────────────────────────────

    def invalidate(
        self,
        path: PathArg | None = None,
        *,
        scope: str = "all",
    ) -> int:
        """Drop cached entries; return the number dropped.

        Args:
            path: Drop only this entry (and its descendants if a dir).
                ``None`` drops based on ``scope``.
            scope: ``"all"`` drops every entry and removes the mirror
                directory.  ``"indices"`` drops only entries whose
                basename is in :data:`INDEX_FILE_NAMES` (lets the UI
                refresh navigation without throwing away cached log
                bytes).
        """
        if path is not None:
            key = self.resolve(path)
            return self._invalidate(key, recursive=True)
        if scope == "indices":
            keys = [k for k in self._index if self._inner.basename(k) in INDEX_FILE_NAMES]
            for key in keys:
                self._invalidate(key)
            # Dir listings are part of navigation — drop them so refresh
            # re-lists containers instead of replaying a pinned tree.
            dir_count = len(self._dir_index)
            self._dir_index.clear()
            self._indexed = False
            self._persist_sidecar()
            return len(keys) + dir_count
        if scope == "all":
            count = len(self._index)
            self._index.clear()
            self._dir_index.clear()
            self._mirrored_bytes = 0
            if self._files_root.exists():
                with contextlib.suppress(OSError):
                    shutil.rmtree(self._files_root)
            # Index is gone — caller must re-run ``index()`` / ``prepare``.
            self._indexed = False
            self._ensure_mirror_dirs()
            self._persist_sidecar()
            return count
        raise ValueError(f"unknown scope {scope!r}")

    # ── Internals ───────────────────────────────────────────────────────

    def _pinned_entry(self, key: str) -> _Entry | None:
        """Return a trusted local entry, or None if we must touch remote.

        Pin mode (``ttl_seconds > 0``): any recorded entry wins until an
        **active** refresh (``force_fetch`` / open / user Refresh).
        Strict mode (``ttl_seconds == 0``): never pin.
        Active refresh thread sets ``_tls.force_fetch`` so it always hits remote.
        """
        if getattr(self._tls, "force_fetch", False):
            return None
        if self._ttl_seconds == 0:
            return None
        entry = self._index.get(key)
        if entry is not None and self._is_stale(entry.fetched_at):
            return None
        return entry

    def _pinned_dir(self, key: str) -> _DirListing | None:
        if getattr(self._tls, "force_fetch", False):
            return None
        if self._ttl_seconds == 0:
            return None
        listing = self._dir_index.get(key)
        if listing is not None and self._is_stale(listing.fetched_at):
            return None
        return listing

    def _is_stale(self, fetched_at: float) -> bool:
        """Whether an entry predates ``revalidate_before`` and must be re-read once.

        A CLI invocation passes its own start time, so each run revalidates
        what it touches exactly once and then serves the rest of its work from
        the refreshed pin — not the same thing as giving up pinning, which
        would put an SSH round-trip back on every call.
        """
        cutoff = self._revalidate_before
        return cutoff is not None and fetched_at < cutoff

    # Back-compat aliases used by older call sites / tests.
    def _fresh_entry(self, key: str) -> _Entry | None:
        return self._pinned_entry(key)

    def _fresh_dir(self, key: str) -> _DirListing | None:
        return self._pinned_dir(key)

    def _revalidate_file_entry(self, key: str, entry: _Entry) -> bool:
        """Return True when remote file is unchanged; refresh ``fetched_at``.

        Used only in strict mode (``ttl_seconds==0``) when the local mirror
        still has bytes. A single remote ``stat`` is cheaper than re-
        downloading navigation metadata over SSH.
        """
        remote_stat = self._safe_stat(key)
        if remote_stat is None or not remote_stat.is_file:
            return False
        if remote_stat.size != entry.size:
            return False
        # Float mtimes from SSH can differ at sub-second precision across
        # serialisations; treat near-equality as a match.
        if abs(remote_stat.mtime - entry.mtime) > 1e-3:
            return False
        self._record(key, kind="file", size=entry.size, mtime=entry.mtime)
        return True

    def _record(
        self, key: str, *, kind: str, size: int, mtime: float, mirrored: bool = False
    ) -> None:
        now = time.time()
        with self._lock:
            previous = self._index.get(key)
            if previous is not None and previous.mirrored and not mirrored:
                self._mirrored_bytes -= previous.size
            if mirrored and (previous is None or not previous.mirrored):
                self._mirrored_bytes += size
            self._index[key] = _Entry(
                size=size,
                mtime=mtime,
                fetched_at=now,
                kind=kind,
                mirrored=mirrored,
                last_used=now,
            )
            self._persist_sidecar()

    def _touch_entry(self, key: str) -> None:
        """Mark *key* as just-used so LRU eviction spares it.

        Deliberately does **not** persist: recency is a hint, and writing the
        sidecar on every cache *hit* would reintroduce the write amplification
        the debounce exists to remove.
        """
        with self._lock:
            entry = self._index.get(key)
            if entry is not None:
                self._index[key] = replace(entry, last_used=time.time())

    def _maybe_write_mirror(self, key: str, mirror_path: Path, data: bytes) -> bool:
        """Mirror *data* unless it is too large; evict LRU files to stay in budget.

        Returns whether the bytes were written. An over-cap file is still
        returned to the caller — it is just never stored, so previewing one
        4 GB trajectory cannot evict the whole navigation tree.
        """
        if len(data) > self._mirror_max_file_bytes:
            return False
        with self._lock:
            self._evict_to_budget(len(data), keep=key)
        self._write_mirror(mirror_path, data)
        return True

    def _evict_to_budget(self, incoming: int, *, keep: str) -> None:
        """Drop least-recently-used non-navigation mirror files to fit *incoming*.

        Caller must hold ``_lock``. Navigation metadata is never evicted: it is
        what makes the tree load without SSH, and it is tiny compared to the
        log/artifact bytes that actually fill the budget.
        """
        if self._mirrored_bytes + incoming <= self._mirror_budget_bytes:
            return
        candidates = [
            (entry.last_used, key)
            for key, entry in self._index.items()
            if entry.mirrored and key != keep and not _is_navigation(key)
        ]
        candidates.sort()
        for _, key in candidates:
            if self._mirrored_bytes + incoming <= self._mirror_budget_bytes:
                return
            self._drop_mirror(key)

    def _drop_mirror(self, key: str) -> None:
        """Delete *key*'s mirrored bytes but keep its index entry.

        The entry is what lets ``stat`` / ``exists`` / ``is_dir`` keep
        answering with zero round-trips; only the bytes are reclaimable.
        """
        entry = self._index.get(key)
        if entry is None or not entry.mirrored:
            return
        mirror_path = self._mirror_for(key)
        with contextlib.suppress(OSError):
            if mirror_path.exists():
                mirror_path.unlink()
        self._index[key] = replace(entry, mirrored=False)
        self._mirrored_bytes -= entry.size
        self._persist_sidecar()

    def _forget(self, key: str) -> None:
        """Drop one index entry, keeping the mirrored-byte total consistent."""
        entry = self._index.pop(key, None)
        if entry is not None and entry.mirrored:
            self._mirrored_bytes -= entry.size

    def _invalidate(self, key: str, *, recursive: bool = False) -> int:
        dropped = 0
        if key in self._index:
            self._forget(key)
            dropped += 1
        if recursive:
            prefix = key.rstrip("/") + "/"
            for k in list(self._index):
                if k.startswith(prefix):
                    self._forget(k)
                    dropped += 1
            for k in list(self._dir_index):
                if k == key or k.startswith(prefix):
                    del self._dir_index[k]
        # Always invalidate the parent dir listing.
        self._invalidate_dir(self._inner.dirname(key))
        # Best-effort mirror eviction.
        mirror_path = self._mirror_for(key)
        if self._local.exists(mirror_path):
            with contextlib.suppress(OSError):
                if recursive and self._local.is_dir(mirror_path):
                    shutil.rmtree(mirror_path)
                else:
                    self._local.remove(mirror_path)
        self._persist_sidecar()
        return dropped

    def _invalidate_dir(self, dir_key: str) -> None:
        self._dir_index.pop(dir_key, None)

    def _mirror_for(self, abs_path: str) -> Path:
        # Strip any leading slashes so we stay inside files/.
        relative = os.fspath(abs_path).lstrip("/")
        return self._files_root / relative

    def _write_mirror(self, mirror_path: Path, data: bytes) -> None:
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = mirror_path.with_suffix(mirror_path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, mirror_path)  # noqa: PTH105

    def _safe_stat(self, key: str) -> StatResult | None:
        try:
            return self._inner.stat(key)
        except Exception:
            return None

    def _load_sidecar(self) -> None:
        if not self._sidecar.exists():
            return
        try:
            raw = json.loads(self._sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "cache sidecar at %s unreadable; starting empty (%s)", self._sidecar, exc
            )
            return
        if not isinstance(raw, dict) or raw.get("version") != _SIDECAR_VERSION:
            logger.warning("cache sidecar at %s has wrong version; starting empty", self._sidecar)
            return
        # Pin-until-refresh: load entries as-is.  ``fetched_at`` is advisory
        # only (strict mode / debugging); positive TTL never auto-expires.
        entries = raw.get("entries", {}) or {}
        for key, payload in entries.items():
            try:
                self._index[key] = _Entry(**payload)
            except TypeError:
                continue
        dirs = raw.get("dirs", {}) or {}
        for key, payload in dirs.items():
            try:
                entries = tuple(DirEntry(**row) for row in payload.get("entries", ()))
                fetched_at = float(payload.get("fetched_at", 0.0))
                self._dir_index[key] = _DirListing(entries=entries, fetched_at=fetched_at)
            except (AttributeError, TypeError, ValueError):
                continue

    def _persist_sidecar(self) -> None:
        """Mark the sidecar dirty; write now, on batch exit, or after a debounce.

        Inside ``batched()`` the write happens once on exit. Outside it, the
        sidecar is written at most once per second and a timer catches the
        trailing edge — without this, a walk that records N entries rewrites
        the whole index N times, which is O(N²) bytes.
        """
        self._sidecar_dirty = True
        if self._defer_persist:
            return
        now = time.monotonic()
        if now - self._sidecar_last_write >= _SIDECAR_DEBOUNCE_SECONDS:
            self._write_sidecar()
            return
        self._arm_sidecar_timer()

    def _arm_sidecar_timer(self) -> None:
        """Schedule one trailing sidecar write; idempotent while armed."""
        if self._sidecar_timer is not None and self._sidecar_timer.is_alive():
            return
        timer = threading.Timer(_SIDECAR_DEBOUNCE_SECONDS, self.flush)
        timer.daemon = True
        self._sidecar_timer = timer
        timer.start()

    @contextlib.contextmanager
    def batched(self) -> Iterator[None]:
        """Defer sidecar writes for the duration of a bulk operation.

        Per-op cache records/invalidations only mark the sidecar dirty; the
        full serialization runs once on exit. Use around bulk walks (e.g.
        :func:`prefetch_workspace_indices`) to avoid O(records²) rewrites.
        Re-entrant: nested ``batched()`` flush only at the outermost exit.
        """
        if self._defer_persist:
            yield  # already batching — inner block is a no-op wrapper
            return
        self._defer_persist = True
        try:
            yield
        finally:
            self._defer_persist = False
            self.flush()

    def flush(self) -> None:
        """Write the sidecar if it has pending (deferred/debounced) changes."""
        timer = self._sidecar_timer
        if timer is not None:
            timer.cancel()
            self._sidecar_timer = None
        if self._sidecar_dirty:
            self._write_sidecar()

    def _write_sidecar(self) -> None:
        """Atomically persist ``_index.json``. Missing parent dirs are recreated.

        External ``rm -rf`` of the mirror mid-flight (or a brand-new remote
        open with no prior sidecar) must not leave the cache permanently
        mute — we re-mkdir and retry once before warning.
        """
        payload = {
            "version": _SIDECAR_VERSION,
            "ttl_seconds": self._ttl_seconds,
            "entries": {k: asdict(v) for k, v in self._index.items()},
            "dirs": {
                k: {
                    "entries": [asdict(e) for e in v.entries],
                    "fetched_at": v.fetched_at,
                }
                for k, v in self._dir_index.items()
            },
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        tmp = self._sidecar.with_suffix(self._sidecar.suffix + ".tmp")

        def _attempt() -> None:
            self._ensure_mirror_dirs()
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self._sidecar)  # noqa: PTH105

        self._sidecar_last_write = time.monotonic()
        try:
            _attempt()
            self._sidecar_dirty = False
        except OSError:
            # Parent may have vanished between mkdir and replace (e.g. another
            # process wiped ``~/.molexp/remote_cache/<name>``). Retry once.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            try:
                _attempt()
                self._sidecar_dirty = False
            except OSError as exc:
                logger.warning("cache sidecar write failed at %s: %s", self._sidecar, exc)
                with contextlib.suppress(OSError):
                    tmp.unlink(missing_ok=True)


@dataclass
class _PrefetchState:
    warnings: list[PrefetchWarning] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_warning(self, path: str, reason: str) -> None:
        with self.lock:
            self.warnings.append(PrefetchWarning(path=path, reason=reason))


def _prefetch_workers(explicit: int | None) -> int:
    if explicit is not None:
        return max(1, explicit)
    raw = os.environ.get("MOLEXP_PREFETCH_WORKERS", "").strip()
    if raw:
        with contextlib.suppress(ValueError):
            return max(1, int(raw))
    return _DEFAULT_PREFETCH_WORKERS


def _parallel_map[T, R](
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    max_workers: int,
    force_fetch_fs: CachedRemoteFileSystem | None = None,
) -> list[R]:
    """Map *fn* over *items*, parallel when ``max_workers > 1`` and |items| > 1.

    Preserves input order (submit all, collect in order).  When *force_fetch_fs*
    is set, every worker thread inherits ``force_fetch`` so active refreshes
    re-pull remote bytes (``threading.local`` is not inherited otherwise).
    """
    if not items:
        return []
    if max_workers <= 1 or len(items) == 1:
        return [fn(item) for item in items]
    workers = min(max_workers, len(items))

    def _init() -> None:
        if force_fetch_fs is not None:
            force_fetch_fs._tls.force_fetch = True

    with ThreadPoolExecutor(max_workers=workers, initializer=_init) as pool:
        futures = [pool.submit(fn, item) for item in items]
        return [fut.result() for fut in futures]


def prefetch_workspace_indices(
    workspace: Workspace,
    *,
    max_workers: int | None = None,
) -> list[PrefetchWarning]:
    """Outside-in parallel walk of entity metadata through ``workspace._fs``.

    Levels (each level fully completes before the next — outer → inner):

    1. **Workspace** — ``workspace.json`` + ``project.json`` index +
       ``listdir(projects/)``.
    2. **Projects** — all ``project.json`` in parallel, then per-project
       experiment indexes + ``listdir(experiments/)`` in parallel.
    3. **Experiments** — all ``experiment.json`` in parallel, then per-
       experiment run indexes + ``listdir(runs/)`` in parallel.
    4. **Runs** — all ``run.json`` in parallel.

    Concurrency is per level (default 8 workers; ``MOLEXP_PREFETCH_WORKERS``
    or *max_workers*).  When the FS is a :class:`CachedRemoteFileSystem`,
    call under :meth:`~CachedRemoteFileSystem.force_fetch` so an **active**
    refresh re-pulls remote bytes instead of replaying the pin.

    Missing or unreadable nodes become :class:`PrefetchWarning` entries;
    the walk continues so one bad project does not blank the tree.

    Returns:
        Warnings collected during the walk (order not guaranteed under
        parallel execution).
    """
    state = _PrefetchState()
    fs = workspace._fs
    root = str(workspace.root)
    workers = _prefetch_workers(max_workers)
    # Bulk path: two round-trips for the whole tree, regardless of run count.
    if isinstance(fs, CachedRemoteFileSystem) and _bulk_prefetch(fs, root):
        return list(state.warnings)
    # Propagate active-refresh force_fetch into worker threads (TLS is not
    # inherited by ThreadPoolExecutor workers).
    force_fs: CachedRemoteFileSystem | None = None
    if isinstance(fs, CachedRemoteFileSystem) and getattr(fs._tls, "force_fetch", False):
        force_fs = fs

    batch = (
        fs.batched()  # ty: ignore[call-non-callable]
        if hasattr(fs, "batched")
        else contextlib.nullcontext()
    )
    # Callers that already entered force_fetch (index/refresh) keep it;
    # bare prefetch still benefits from parallel structure on any FS.
    with batch:
        # ── L0: workspace root (serial — tiny) ──────────────────────────
        _safe_read(fs, fs.join(root, "workspace.json"), state)
        projects_dir = fs.join(root, "projects")
        _safe_read(fs, fs.join(root, "project.json"), state, warn_on_missing=False)
        try:
            project_names = list(fs.listdir(projects_dir))
        except FileNotFoundError:
            return list(state.warnings)
        except Exception as exc:
            state.add_warning(projects_dir, str(exc))
            return list(state.warnings)

        # ── L1: project.json in parallel ────────────────────────────────
        def _load_project(name: str) -> str | None:
            meta = fs.join(projects_dir, name, "project.json")
            return name if _safe_read(fs, meta, state) is not None else None

        healthy_projects = [
            n
            for n in _parallel_map(
                _load_project,
                project_names,
                max_workers=workers,
                force_fetch_fs=force_fs,
            )
            if n
        ]

        # ── L1b: listdir experiments/ per project (parallel) ────────────
        def _list_experiments(project_name: str) -> list[tuple[str, str]]:
            project_dir = fs.join(projects_dir, project_name)
            experiments_dir = fs.join(project_dir, "experiments")
            _safe_read(fs, fs.join(project_dir, "experiment.json"), state, warn_on_missing=False)
            try:
                names = fs.listdir(experiments_dir)
            except FileNotFoundError:
                return []
            except Exception as exc:
                state.add_warning(experiments_dir, str(exc))
                return []
            return [(project_name, n) for n in names]

        exp_pairs: list[tuple[str, str]] = []
        for pairs in _parallel_map(
            _list_experiments,
            healthy_projects,
            max_workers=workers,
            force_fetch_fs=force_fs,
        ):
            exp_pairs.extend(pairs)

        # ── L2: experiment.json in parallel ─────────────────────────────
        def _load_experiment(pair: tuple[str, str]) -> tuple[str, str] | None:
            project_name, exp_name = pair
            meta = fs.join(projects_dir, project_name, "experiments", exp_name, "experiment.json")
            return pair if _safe_read(fs, meta, state) is not None else None

        healthy_exps = [
            p
            for p in _parallel_map(
                _load_experiment,
                exp_pairs,
                max_workers=workers,
                force_fetch_fs=force_fs,
            )
            if p
        ]

        # ── L2b: listdir runs/ per experiment (parallel) ────────────────
        def _list_runs(pair: tuple[str, str]) -> list[tuple[str, str, str]]:
            project_name, exp_name = pair
            experiment_dir = fs.join(projects_dir, project_name, "experiments", exp_name)
            runs_dir = fs.join(experiment_dir, "runs")
            _safe_read(fs, fs.join(experiment_dir, "run.json"), state, warn_on_missing=False)
            try:
                names = fs.listdir(runs_dir)
            except FileNotFoundError:
                return []
            except Exception as exc:
                state.add_warning(runs_dir, str(exc))
                return []
            return [(project_name, exp_name, n) for n in names]

        run_triples: list[tuple[str, str, str]] = []
        for triples in _parallel_map(
            _list_runs, healthy_exps, max_workers=workers, force_fetch_fs=force_fs
        ):
            run_triples.extend(triples)

        # ── L3: run.json in parallel (innermost — usually the bulk) ─────
        def _load_run(triple: tuple[str, str, str]) -> None:
            project_name, exp_name, run_name = triple
            meta = fs.join(
                projects_dir,
                project_name,
                "experiments",
                exp_name,
                "runs",
                run_name,
                "run.json",
            )
            _safe_read(fs, meta, state)

        _parallel_map(_load_run, run_triples, max_workers=workers, force_fetch_fs=force_fs)

    return list(state.warnings)


#: Depth of ``projects/<p>/experiments/<e>/runs/<r>/_ops`` below the root.
_WORKSPACE_MAX_DEPTH = 7

#: Per-run navigation metadata the UI asks for immediately after the tree.
NAVIGATION_FETCH_NAMES: frozenset[str] = frozenset(
    {"workspace.json", "project.json", "experiment.json", "run.json", "assets.json", "meta.yaml"}
)

#: Never descended into by the bulk walk — machine output, not navigation.
_BULK_PRUNE_DIRS: frozenset[str] = frozenset(
    {"executions", "artifacts", "cache", "logs", "jobs", "source", "metrics", ".ckpt"}
)

#: Ceiling for a bulk-fetched metadata file; a stray huge one is left to the
#: lazy path rather than blowing up a single tar stream.
_BULK_MAX_FILE_BYTES = 1024 * 1024


def _bulk_prefetch(fs: CachedRemoteFileSystem, root: str) -> bool:
    """Warm the whole navigation tree in two round-trips, if the inner FS can.

    One ``walk_entries`` populates every directory listing (and, through
    ``scandir``'s child recording, the stat of every entity directory); one
    ``fetch_files`` pulls every navigation file as a single tar stream. The
    per-level walk below needs at least one round-trip *per run* for the same
    data, so this is the difference between a remote workspace being usable
    and not.

    Returns:
        ``True`` when the bulk path ran and the tree is warm; ``False`` when
        the inner FS lacks the accelerators (or the host lacks GNU ``find``),
        so the caller falls back to the per-level walk.
    """
    inner = fs.inner
    walk_entries = getattr(inner, "walk_entries", None)
    fetch_files = getattr(inner, "fetch_files", None)
    if walk_entries is None or fetch_files is None:
        return False
    try:
        with fs.batched():
            listings = walk_entries(root, max_depth=_WORKSPACE_MAX_DEPTH, prune=_BULK_PRUNE_DIRS)
            if not listings:
                return False
            fs.absorb_listings(listings)
            files = fetch_files(
                root,
                names=NAVIGATION_FETCH_NAMES,
                max_bytes=_BULK_MAX_FILE_BYTES,
                prune=_BULK_PRUNE_DIRS,
            )
            fs.absorb_files(files)
    except Exception:
        # Falling back is a normal outcome (no GNU find, an inner FS without
        # the accelerators), not an error the operator needs to see — the
        # per-level walk raises its own warnings if anything is really wrong.
        logger.debug("bulk prefetch unavailable for %s; using per-level walk", root, exc_info=True)
        return False
    return True


def _safe_read(
    fs: FileSystem,
    path: str,
    state: _PrefetchState,
    *,
    warn_on_missing: bool = True,
) -> str | None:
    try:
        return fs.read_text(path)
    except FileNotFoundError as exc:
        if warn_on_missing:
            state.add_warning(path, f"not found: {exc}")
        return None
    except Exception as exc:
        state.add_warning(path, str(exc))
        return None


def _read_container_children(
    fs: FileSystem,
    *,
    container_dir: str,
    index_path: str,
    per_child_metadata: str,
    state: _PrefetchState,
    max_workers: int = 1,
) -> list[str]:
    """Warm the children-index, then list the container (optional parallel meta).

    Kept for callers/tests that target a single container.  The main walk
    uses the outside-in levels in :func:`prefetch_workspace_indices`.
    """
    _safe_read(fs, index_path, state, warn_on_missing=False)
    try:
        names = list(fs.listdir(container_dir))
    except FileNotFoundError:
        return []
    except Exception as exc:
        state.add_warning(container_dir, str(exc))
        return []

    def _one(name: str) -> str | None:
        meta_path = fs.join(container_dir, name, per_child_metadata)
        return name if _safe_read(fs, meta_path, state) is not None else None

    return [n for n in _parallel_map(_one, names, max_workers=max_workers) if n]
