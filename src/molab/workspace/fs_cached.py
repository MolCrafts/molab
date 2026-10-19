"""Caching :class:`FileSystem` decorator — lazy-download mirror for
remote workspaces.

Wraps an inner :class:`~molab.workspace.fs.FileSystem` (only meaningful
for :class:`~molab.workspace.fs_remote.RemoteFileSystem`) and maintains
a server-side mirror under ``<mirror_root>/files/...``.

**Pin-until-refresh policy** (default): once a path is in the local
index/mirror it is trusted until explicitly refreshed. Age does **not**
trigger automatic revalidation — the operator refreshes via
``POST /api/workspace/cache/refresh`` (or ``invalidate``).  Cache misses
still go to the remote FS and populate the mirror.

``cache_mode="strict"`` fetches content on every read, including when size
and mtime are unchanged.

Index files are not special-cased — they are just paths.  The eager
prefetch helper :func:`prefetch_workspace_indices` walks the workspace by
``listdir`` plus the per-entity metadata files
(``workspace.json`` / ``project.json`` / ``experiment.json`` / ``run.json``
/ ``execution.json``) through :meth:`read_text`, so the navigation tree is
populated as a side-effect of caching.  Entity ``*.json`` is the sole
truth source.

Layer rule: lives in the workspace layer next to ``fs_local.py`` and
``fs_remote.py``; reaches only into sibling FS modules and the
:func:`atomic_write_json` primitive.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable, Generator, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from molab.atomicio import atomic_write_bytes, atomic_write_json

from .execution_dirs import execution_dir_names
from .fs import DirEntry, FileSystem, PathArg, StatResult
from .fs_local import LocalFileSystem
from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .workspace import Workspace

__all__ = [
    "INDEX_FILE_NAMES",
    "CachedRemoteFileSystem",
    "IndexProgress",
    "PrefetchWarning",
    "prefetch_workspace_indices",
]


# Outside-in parallel prefetch: concurrent SSH ops per level. Override with
# ``MOLAB_PREFETCH_WORKERS`` (1 = serial, useful in tests).
_DEFAULT_PREFETCH_WORKERS = 8

logger = logging.getLogger(__name__)


class _IndexFileNames(frozenset[str]):
    """Files whose basename identifies them as a navigation-index artefact.

    Entity files and the attempt record. ``execution.json`` is listed so
    ``invalidate(scope="indices")`` — the ``POST /cache/refresh`` path
    (``server/routes/workspace.py``) — evicts cached attempt records; a refresh
    never replays a stale run status.
    """


INDEX_FILE_NAMES = _IndexFileNames(
    {
        "workspace.json",
        "project.json",
        "experiment.json",
        "run.json",
        "execution.json",
    }
)

_SIDECAR_FILENAME = "_index.json"
_SIDECAR_VERSION = 1


@dataclass(frozen=True)
class _Entry:
    """One cached file/dir/missing record."""

    size: int
    mtime: float
    fetched_at: float
    kind: str  # "file" | "dir" | "missing"


@dataclass(frozen=True)
class _DirEntry:
    """One cached listdir result."""

    names: tuple[str, ...]
    fetched_at: float


@dataclass(frozen=True)
class PrefetchWarning:
    """One node that failed during :func:`prefetch_workspace_indices`."""

    path: str
    reason: str


@dataclass
class IndexProgress:
    """Live remote-index progress for the status bar.

    *counting* — recursive total is still being computed.
    *fetching* — ``done/total`` advance as files are force-fetched.
    *done* / *error* — terminal.
    """

    phase: str = "idle"  # idle | counting | fetching | done | error
    total: int = 0
    done: int = 0
    message: str = ""

    @property
    def percent(self) -> float | None:
        if self.total <= 0:
            return None
        return min(100.0, 100.0 * self.done / self.total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "total": self.total,
            "done": self.done,
            "percent": self.percent,
            "message": self.message,
        }


class CachedRemoteFileSystem:
    """Lazy-download mirror over any :class:`FileSystem`.

    **Default (``cache_mode="pinned"``)**: pin-until-refresh.  Any path present
    in the sidecar/mirror is served locally with **zero** remote I/O until
    the operator invalidates/refreshes.  Mutations still go to the inner
    FS and invalidate the affected entry.

    **Strict (``cache_mode="strict"``)**: every read fetches remote content;
    equal metadata never proves content freshness.

    The mirror layout reflects the remote path verbatim (leading ``/``
    stripped) under ``<mirror_root>/files/``, so a remote path
    ``/home/me/run/log.txt`` ends up at ``<mirror_root>/files/home/me/
    run/log.txt``.  This stays debuggable and lets ``find`` walk the
    mirror.

    Args:
        inner: The :class:`FileSystem` to cache.
        mirror_root: Local directory holding the mirror.  Created on
            first write.
        cache_mode: ``pinned`` reuses content until explicit refresh;
            ``strict`` fetches content on every read.
    """

    def __init__(
        self,
        inner: FileSystem,
        *,
        mirror_root: Path | str,
        cache_mode: str = "pinned",
    ) -> None:
        if cache_mode not in {"pinned", "strict"}:
            raise ValueError("cache_mode must be pinned or strict")
        self._inner = inner
        self._local = LocalFileSystem()
        self._mirror_root = Path(mirror_root)
        self._files_root = self._mirror_root / "files"
        self._cache_mode = cache_mode
        self._index: dict[str, _Entry] = {}
        self._dir_index: dict[str, _DirEntry] = {}
        self._sidecar = self._mirror_root / _SIDECAR_FILENAME
        # Sidecar write batching: while ``_defer_persist`` is set (inside
        # ``batched()``), per-op writes only mark ``_sidecar_dirty`` and the
        # full serialization happens once on batch exit — turning a bulk walk
        # (e.g. ``prefetch_workspace_indices``) from O(records²) into O(records).
        self._defer_persist = 0
        self._sidecar_dirty = False
        # Lifecycle flags — a brand-new remote root has no sidecar; that is
        # normal. ``connect`` / ``index`` (or ``prepare``) flip these once
        # the local mirror is ready and navigation metadata is warm.
        self._connected = False
        self._indexed = False
        self._remote_root: str | None = None
        self._lock = threading.RLock()
        self._generation = 0
        self._index_thread: threading.Thread | None = None
        self._indexing = False
        self._progress = IndexProgress()
        # Per-thread: active refresh bypasses pin and re-fetches from remote.
        # UI threads keep serving the pinned mirror while a refresh runs.
        self._tls = threading.local()
        # Always own the local mirror tree up-front so a missing
        # ``_index.json`` never surfaces as "Path not found" on first write.
        self._ensure_mirror_dirs()
        self._load_sidecar()
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
    def cache_mode(self) -> str:
        return self._cache_mode

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
        """True while a background :meth:`schedule_refresh` walk is in flight."""
        return self._indexing

    @property
    def progress(self) -> IndexProgress:
        """Snapshot of the live index walk (safe to read from any thread)."""
        with self._lock:
            p = self._progress
            return IndexProgress(
                phase=p.phase,
                total=p.total,
                done=p.done,
                message=p.message,
            )

    def _set_progress(
        self,
        *,
        phase: str | None = None,
        total: int | None = None,
        done: int | None = None,
        message: str | None = None,
        inc_done: int = 0,
    ) -> None:
        with self._lock:
            if phase is not None:
                self._progress.phase = phase
            if total is not None:
                self._progress.total = max(0, total)
            if done is not None:
                self._progress.done = max(0, done)
            if inc_done:
                self._progress.done = max(0, self._progress.done + inc_done)
            if message is not None:
                self._progress.message = message

    def cached_paths(self) -> list[str]:
        """Snapshot of cached file/dir/missing paths — handy in tests."""
        with self._lock:
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
        except Exception:
            self._connected = False
            raise
        if not reachable:
            self._connected = False
            raise FileNotFoundError(f"remote root not found: {root}")
        # Missing sidecar is normal — write current in-memory state (often empty).
        if not self._sidecar.exists():
            self._write_sidecar()
        self._connected = True

    @contextlib.contextmanager
    def force_fetch(self) -> Generator[None]:
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

        Progress for the status bar:

        1. *fetching* — entity metadata force-fetched (optional quick count
           for a denominator; never blocks the walk on a long ``find``)
        2. *done*
        """
        self._remote_root = str(workspace.root)
        if not self._connected:
            self.connect(str(workspace.root))
        root = str(workspace.root)

        # The semantic walk supplies progress; avoid a separate traversal of all payloads.
        total = 0
        self._set_progress(
            phase="fetching",
            total=max(total, 0),
            done=0,
            message="Syncing remote tree…",
        )
        try:
            with self.force_fetch():
                warnings = prefetch_workspace_indices(
                    workspace,
                    on_file=self._on_index_file,
                )
            # Prefetch uses batched(); flush guarantees the sidecar is on disk.
            self.flush()
            if not self._sidecar.exists():
                self._write_sidecar()
            self._indexed = True
            self._indexing = False
            # Snap to 100% so a total that over-counted still completes.
            with self._lock:
                tot = max(self._progress.total, self._progress.done, 1)
                self._progress.total = tot
                self._progress.done = tot
            self._set_progress(phase="done", message="Remote index ready")
            return warnings
        except Exception as exc:
            self._indexing = False
            self._set_progress(phase="idle", message="")
            logger.debug("remote index failed for %s: %s", root, exc)
            raise

    def _on_index_file(self, _path: str) -> None:
        """Progress tick for each file force-fetched during index."""
        with self._lock:
            self._progress.done += 1
            done = self._progress.done
            total = max(self._progress.total, done)
            # If we discover more entity files than the find total predicted
            # (e.g. race / find missed), grow the denominator.
            if done > self._progress.total:
                self._progress.total = done
                total = done
            if total > 0:
                self._progress.message = f"Syncing remote tree ({done}/{total})…"
            else:
                self._progress.message = f"Syncing remote tree ({done})…"

    def schedule_refresh(self, workspace: Workspace) -> None:
        """Run :meth:`index` on a daemon thread (non-blocking active refresh).

        Always starts a new force-fetch when idle — linking a remote must
        re-pull even if a previous pin exists. Idempotent while a walk is
        already in flight.
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
                except Exception as exc:
                    # Quiet — 2FA / offline is expected until the user connects.
                    logger.debug("background remote index skipped for %s: %s", root, exc)
                    self._indexing = False
                    self._set_progress(phase="idle", message="")

            self._index_thread = threading.Thread(
                target=_run,
                name="molab-remote-index",
                daemon=True,
            )
            self._index_thread.start()

    def prepare(
        self,
        workspace: Workspace,
        *,
        block_index: bool = False,
        refresh_on_open: bool = True,
    ) -> list[PrefetchWarning]:
        """Open path for ``molab serve`` / API.

        * **On open / link** (``refresh_on_open=True``): always force-fetch
          from remote (even when a pin exists). Default is **async** so the
          UI can poll :attr:`progress` for a file-count progress bar;
          pass ``block_index=True`` to wait for the walk (CLI / tests).
        * **Cold**: probe SSH first, then the same refresh path.
        """
        self._remote_root = str(workspace.root)
        if not refresh_on_open and self._indexed:
            # A warm pin is read without replacing previously cached content.
            return []
        if not self._connected:
            self.connect(str(workspace.root))
        if block_index:
            return self.index(workspace)
        # Async force-refresh — UI polls GET /api/workspace/cache/status.
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
        with self._lock:
            key = self.resolve(path)
            entry = self._pinned_entry(key)
            if entry is not None:
                return entry.kind != "missing"
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        result = self._inner.exists(key)
        if not result:
            # Negative cache: future ``exists`` returns False without SSH.
            self._record(key, generation=generation, kind="missing", size=0, mtime=0.0)
        return result

    def is_dir(self, path: PathArg) -> bool:
        with self._lock:
            key = self.resolve(path)
            entry = self._pinned_entry(key)
            if entry is not None:
                return entry.kind == "dir"
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        result = self._inner.is_dir(key)
        if result:
            self._record(key, generation=generation, kind="dir", size=0, mtime=time.time())
        return result

    def is_file(self, path: PathArg) -> bool:
        with self._lock:
            key = self.resolve(path)
            entry = self._pinned_entry(key)
            if entry is not None:
                return entry.kind == "file"
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        result = self._inner.is_file(key)
        if result:
            # Don't fetch yet — just record what we learned.
            stat_value = self._safe_stat(key)
            if stat_value is not None:
                self._record(
                    key,
                    generation=generation,
                    kind="file",
                    size=stat_value.size,
                    mtime=stat_value.mtime,
                )
        return result

    # ── Directory operations ────────────────────────────────────────────

    def mkdir(self, path: PathArg, *, parents: bool = True, exist_ok: bool = True) -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=False):
            self._inner.mkdir(key, parents=parents, exist_ok=exist_ok)

    def listdir(self, path: PathArg) -> list[str]:
        with self._lock:
            key = self.resolve(path)
            cached = self._pinned_dir(key)
            if cached is not None:
                return list(cached.names)
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        names = self._inner.listdir(key)
        with self._lock:
            if generation != self._generation:
                return names
            self._dir_index[key] = _DirEntry(names=tuple(names), fetched_at=time.time())
            self._persist_sidecar()
        return names

    def scandir(self, path: PathArg, *, with_stat: bool = True) -> list[DirEntry]:
        """List a directory with per-entry type and metadata in one round-trip.

        Forwarded to the inner filesystem, whose listing already carries type,
        size and mtime; the names are recorded in the directory index so a
        following ``listdir`` is served locally.
        """
        key = self.resolve(path)
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        entries = self._inner.scandir(key, with_stat=with_stat)
        with self._lock:
            if generation != self._generation:
                return entries
            self._dir_index[key] = _DirEntry(
                names=tuple(e.name for e in entries), fetched_at=time.time()
            )
            self._persist_sidecar()
        return entries

    def glob(self, path: PathArg, pattern: str) -> Iterable[str]:
        # Glob is intentionally uncached — patterns are open-ended and
        # caching them risks staleness on every directory change.
        return self._inner.glob(path, pattern)

    def rglob(self, path: PathArg, pattern: str) -> Iterable[str]:
        return self._inner.rglob(path, pattern)

    # ── Read ────────────────────────────────────────────────────────────

    def read_text(self, path: PathArg, encoding: str = "utf-8") -> str:
        return self.read_bytes(path).decode(encoding)

    def read_range(self, path: PathArg, offset: int, length: int) -> bytes:
        """Read one bounded byte range, from the mirror when the file is pinned.

        A window read must not cost a whole-file transfer, so a miss forwards to
        the inner filesystem's ranged read instead of mirroring the file: a slice
        of a multi-gigabyte artifact would otherwise land under the whole file's
        mirror key.
        """
        if offset < 0 or length < 0:
            raise ValueError(f"read_range needs non-negative offset/length, got {offset}/{length}")
        if length == 0:
            return b""
        with self._lock:
            key = self.resolve(path)
            mirror_path = self._mirror_for(key)
            entry = self._pinned_entry(key)
            if entry is not None and entry.kind == "missing":
                raise FileNotFoundError(key)
            if entry is not None and entry.kind == "file" and self._local.exists(mirror_path):
                return self._local.read_range(mirror_path, offset, length)
        self._ensure_connected()
        return self._inner.read_range(key, offset, length)

    def read_bytes(self, path: PathArg) -> bytes:
        with self._lock:
            key = self.resolve(path)
            mirror_path = self._mirror_for(key)
            entry = self._pinned_entry(key)
            if entry is not None and entry.kind == "file" and self._local.exists(mirror_path):
                return self._local.read_bytes(mirror_path)
            if entry is not None and entry.kind == "missing":
                raise FileNotFoundError(key)
            # Strict reads always fetch content, including equal-size same-second changes.
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        try:
            data = self._inner.read_bytes(key)
        except FileNotFoundError:
            self._record(key, generation=generation, kind="missing", size=0, mtime=0.0)
            raise
        stat_value = self._safe_stat(key)
        size = len(data) if stat_value is None else stat_value.size
        mtime = time.time() if stat_value is None else stat_value.mtime
        with self._lock:
            if generation == self._generation:
                self._write_mirror(mirror_path, data)
                self._record(key, kind="file", size=size, mtime=mtime)
        return data

    def read_many(
        self, paths: Sequence[str], *, max_bytes: int = 262144
    ) -> dict[str, bytes | Exception]:
        """Prime semantic metadata in target-side batches while respecting cache policy."""
        result: dict[str, bytes | Exception] = {}
        missing: list[str] = []
        with self._lock:
            for path in paths:
                key = self.resolve(path)
                entry = self._pinned_entry(key)
                mirror = self._mirror_for(key)
                if entry is not None and entry.kind == "file" and self._local.exists(mirror):
                    result[path] = self._local.read_bytes(mirror)
                elif entry is not None and entry.kind == "missing":
                    result[path] = FileNotFoundError(path)
                else:
                    missing.append(path)
        if missing:
            with self._lock:
                generation = self._generation
            self._ensure_connected()
            read_many = getattr(self._inner, "read_many", None)
            batch: dict[str, bytes | Exception] = {}
            if callable(read_many):
                batch = read_many(missing, max_bytes=max_bytes)
            else:
                for path in missing:
                    try:
                        batch[path] = self._inner.read_bytes(path)
                    except OSError as exc:
                        batch[path] = exc
            with self._lock, self.batched():
                for path, value in batch.items():
                    key = self.resolve(path)
                    result[path] = value
                    if generation != self._generation:
                        continue
                    if isinstance(value, bytes):
                        self._write_mirror(self._mirror_for(key), value)
                        self._record(key, kind="file", size=len(value), mtime=0)
                    elif isinstance(value, FileNotFoundError):
                        self._record(key, kind="missing", size=0, mtime=0)
        return result

    def upload(
        self, local: str, remote: str, *, recursive: bool = False, exclude: Sequence[str] = ()
    ) -> None:
        """Transfer a staged upload and invalidate its cached destination."""
        with self._mutation(self.resolve(remote), recursive=True):
            upload = getattr(self._inner, "upload", None)
            if callable(upload):
                upload(local, remote, recursive=recursive, exclude=exclude)
            else:
                self._inner.copy(local, remote)

    def open(self, path: PathArg, mode: str = "r", encoding: str = "utf-8") -> IO[Any]:
        if mode not in {"r", "rt", "rb"}:
            raise ValueError("Remote open supports read-only buffers")
        return (
            io.BytesIO(self.read_bytes(path))
            if mode == "rb"
            else io.StringIO(self.read_text(path, encoding))
        )

    # ── Write ───────────────────────────────────────────────────────────

    def write_text(self, path: PathArg, content: str, *, mode: int = 0o600) -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=False):
            self._inner.write_text(key, content, mode=mode)

    def write_bytes(self, path: PathArg, content: bytes, *, mode: int = 0o600) -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=False):
            self._inner.write_bytes(key, content, mode=mode)

    # ── Mutations ───────────────────────────────────────────────────────

    def rename(self, src: PathArg, dst: PathArg) -> None:
        src_key = self.resolve(src)
        dst_key = self.resolve(dst)
        with self._mutation(src_key, dst_key, recursive=True):
            self._inner.rename(src_key, dst_key)

    def remove(self, path: PathArg, *, recursive: bool = False) -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=recursive):
            self._inner.remove(key, recursive=recursive)

    def copy(self, src: PathArg, dst: PathArg) -> None:
        dst_key = self.resolve(dst)
        with self._mutation(dst_key, recursive=True):
            self._inner.copy(src, dst_key)

    def copytree(self, src: PathArg, dst: PathArg, *, dirs_exist_ok: bool = False) -> None:
        dst_key = self.resolve(dst)
        with self._mutation(dst_key, recursive=True):
            self._inner.copytree(src, dst_key, dirs_exist_ok=dirs_exist_ok)

    # ── Metadata ────────────────────────────────────────────────────────

    def stat(self, path: PathArg) -> StatResult:
        with self._lock:
            key = self.resolve(path)
            entry = self._pinned_entry(key)
            if entry is not None and entry.kind != "missing" and entry.mtime != 0:
                return StatResult(
                    size=entry.size,
                    mtime=entry.mtime,
                    is_dir=entry.kind == "dir",
                    is_file=entry.kind == "file",
                )
        with self._lock:
            generation = self._generation
        self._ensure_connected()
        result = self._inner.stat(key)
        kind = "dir" if result.is_dir else "file" if result.is_file else "missing"
        self._record(key, generation=generation, kind=kind, size=result.size, mtime=result.mtime)
        return result

    def lstat(self, path: PathArg) -> StatResult:
        return self.stat(path)

    def touch(self, path: PathArg) -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=False):
            self._inner.touch(key)

    def chmod(self, path: PathArg, mode: int) -> None:
        with self._mutation(self.resolve(path), recursive=False):
            self._inner.chmod(path, mode)

    def getsize(self, path: PathArg) -> int:
        return self.stat(path).size

    # ── Symlinks ────────────────────────────────────────────────────────

    def symlink(self, src: PathArg, dst: PathArg) -> None:
        dst_key = self.resolve(dst)
        with self._mutation(dst_key, recursive=True):
            self._inner.symlink(src, dst_key)

    # ── Atomic I/O ──────────────────────────────────────────────────────

    def atomic_write_json(self, path: PathArg, data: object) -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=False):
            self._inner.atomic_write_json(key, data)

    def atomic_write_text(self, path: PathArg, content: str, *, encoding: str = "utf-8") -> None:
        key = self.resolve(path)
        with self._mutation(key, recursive=False):
            self._inner.atomic_write_text(key, content, encoding=encoding)

    # ── Cache control ───────────────────────────────────────────────────

    def invalidate_dir_listing(self, path: PathArg) -> None:
        """Drop only the pinned *directory names* for *path* (not file bytes).

        Used by the workspace files API so an expand/list always re-listdir
        from remote. Pin-until-refresh is fine for file contents; empty dir
        pins are not — a folder listed before children existed stays "Empty"
        in the UI until this pin is cleared.
        """
        with self._lock:
            self._generation += 1
            key = self.resolve(path)
            self._dir_index.pop(key, None)
            self._persist_sidecar()

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
        with self._lock:
            self._generation += 1
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

        Pin mode (``cache_mode="pinned"``): any recorded entry wins until an
        **active** refresh (``force_fetch`` / open / user Refresh).
        Strict mode (``cache_mode="strict"``): never pin.
        Active refresh thread sets ``_tls.force_fetch`` so it always hits remote.
        """
        if getattr(self._tls, "force_fetch", False):
            return None
        if self._cache_mode == "strict":
            return None
        return self._index.get(key)

    def _pinned_dir(self, key: str) -> _DirEntry | None:
        if getattr(self._tls, "force_fetch", False):
            return None
        if self._cache_mode == "strict":
            return None
        return self._dir_index.get(key)

    def _record(
        self, key: str, *, kind: str, size: int, mtime: float, generation: int | None = None
    ) -> None:
        with self._lock:
            if generation is not None and generation != self._generation:
                return
            self._index[key] = _Entry(
                size=size,
                mtime=mtime,
                fetched_at=time.time(),
                kind=kind,
            )
            self._persist_sidecar()

    @contextlib.contextmanager
    def _mutation(self, *keys: str, recursive: bool = False) -> Generator[None]:
        """Fence cache observations without holding the mirror lock during remote I/O."""
        with self._lock:
            for key in keys:
                self._invalidate(key, recursive=recursive)
        try:
            yield
        finally:
            # Includes failures with an uncertain outcome: never retain a pin
            # fetched while the remote mutation may have been in progress.
            with self._lock:
                for key in keys:
                    self._invalidate(key, recursive=recursive)

    def _invalidate(self, key: str, *, recursive: bool = False) -> int:
        with self._lock:
            self._generation += 1
            dropped = 0
            if key in self._index:
                del self._index[key]
                dropped += 1
            if recursive:
                prefix = key.rstrip("/") + "/"
                for k in list(self._index):
                    if k.startswith(prefix):
                        del self._index[k]
                        dropped += 1
                for k in list(self._dir_index):
                    if k == key or k.startswith(prefix):
                        del self._dir_index[k]
            # Parent-creating operations may have replaced any negative ancestor
            # pin. Evict those observations and their listings up to our root.
            parent = self._inner.dirname(key)
            boundary = self.resolve(self._remote_root) if self._remote_root else None
            seen: set[str] = set()
            while parent not in seen:
                seen.add(parent)
                self._dir_index.pop(parent, None)
                self._index.pop(parent, None)
                if parent == boundary or parent in {"", ".", "/"}:
                    break
                parent = self._inner.dirname(parent)
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

    def mirror_path(self, path: PathArg) -> Path:
        """Local mirror path for *path* (may not exist yet).

        Public so metrics densify / zarr readers can open a pathlib store after
        :meth:`read_bytes` has populated the mirror — one materialize path for
        remote workspaces.
        """
        return self._mirror_for(self.resolve(path))

    def _mirror_for(self, abs_path: str) -> Path:
        # Strip any leading slashes so we stay inside files/.
        relative = os.fspath(abs_path).lstrip("/")
        return self._files_root / relative

    def _write_mirror(self, mirror_path: Path, data: bytes) -> None:
        atomic_write_bytes(mirror_path, data)

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
                names = tuple(payload.get("names", ()))
                fetched_at = float(payload.get("fetched_at", 0.0))
                self._dir_index[key] = _DirEntry(names=names, fetched_at=fetched_at)
            except (AttributeError, TypeError, ValueError):
                continue

    def _persist_sidecar(self) -> None:
        """Persist now, or defer to batch exit if inside ``batched()``."""
        if self._defer_persist:
            self._sidecar_dirty = True
            return
        self._write_sidecar()

    @contextlib.contextmanager
    def batched(self) -> Generator[None]:
        """Defer sidecar serialization until all overlapping batches finish."""
        with self._lock:
            self._defer_persist += 1
        try:
            yield
        finally:
            with self._lock:
                self._defer_persist -= 1
                if not self._defer_persist:
                    self.flush()

    def flush(self) -> None:
        """Write pending changes under the cache publication lock."""
        with self._lock:
            if self._sidecar_dirty:
                self._write_sidecar()

    def _write_sidecar(self) -> None:
        with self._lock:
            payload = {
                "version": _SIDECAR_VERSION,
                "cache_mode": self._cache_mode,
                "entries": {k: asdict(v) for k, v in self._index.items()},
                "dirs": {
                    k: {"names": list(v.names), "fetched_at": v.fetched_at}
                    for k, v in self._dir_index.items()
                },
            }
            try:
                atomic_write_json(self._sidecar, payload)
            except OSError as exc:
                self._sidecar_dirty = True
                logger.warning("cache sidecar write failed at %s: %s", self._sidecar, exc)
            else:
                self._sidecar_dirty = False


@dataclass
class _PrefetchState:
    prefetched: dict[str, bytes | Exception] = field(default_factory=dict)
    warnings: list[PrefetchWarning] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_warning(self, path: str, reason: str) -> None:
        with self.lock:
            self.warnings.append(PrefetchWarning(path=path, reason=reason))


def _prefetch_workers(explicit: int | None) -> int:
    if explicit is not None:
        return max(1, explicit)
    raw = os.environ.get("MOLAB_PREFETCH_WORKERS", "").strip()
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
    prepare: Callable[[Sequence[T]], None] | None = None,
) -> list[R]:
    """Map *fn* over *items*, parallel when ``max_workers > 1`` and |items| > 1.

    Preserves input order (submit all, collect in order).  When *force_fetch_fs*
    is set, every worker thread inherits ``force_fetch`` so active refreshes
    re-pull remote bytes (``threading.local`` is not inherited otherwise).
    """
    if not items:
        return []
    if prepare is not None:
        result: list[R] = []
        for start in range(0, len(items), 128):
            chunk = items[start : start + 128]
            prepare(chunk)
            result.extend(
                _parallel_map(fn, chunk, max_workers=max_workers, force_fetch_fs=force_fetch_fs)
            )
        return result
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
    on_file: Callable[[str], None] | None = None,
) -> list[PrefetchWarning]:
    """Outside-in parallel walk of entity metadata through ``workspace.fs``.

    Levels (each level fully completes before the next — outer → inner):

    1. **Workspace** — ``workspace.json`` + the project container listing.
    2. **Projects** — all ``project.json`` in parallel, then each project's
       experiment container.
    3. **Experiments** — all ``experiment.json`` in parallel, then each
       experiment's run container.
    4. **Runs** — all ``run.json`` in parallel, then each attempt's
       ``execution.json``.

    Concurrency is per level (default 8 workers; ``MOLAB_PREFETCH_WORKERS``
    or *max_workers*).  When the FS is a :class:`CachedRemoteFileSystem`,
    call under :meth:`~CachedRemoteFileSystem.force_fetch` so an **active**
    refresh re-pulls remote bytes instead of replaying the pin.

    *on_file* is invoked once per successfully force-fetched file path
    (progress bar ticks).

    Missing or unreadable nodes become :class:`PrefetchWarning` entries;
    the walk continues so one bad project does not blank the tree.

    Returns:
        Warnings collected during the walk (order not guaranteed under
        parallel execution).
    """
    state = _PrefetchState()
    fs = workspace.fs
    root = str(workspace.root)
    workers = _prefetch_workers(max_workers)
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
    def prime(paths: list[str]) -> None:
        read_many = getattr(fs, "read_many", None)
        if callable(read_many) and paths:
            state.prefetched.update(read_many(paths))

    with batch:
        # ── L0: workspace root (serial — tiny) ──────────────────────────
        _safe_read(fs, fs.join(root, "workspace.json"), state, on_file=on_file)
        _prefetch_concept_files(fs, root, state, on_file=on_file)
        projects_dir = fs.join(root, PROJECT_CONTAINER)
        try:
            project_names = list(fs.listdir(projects_dir))
        except FileNotFoundError:
            return list(state.warnings)
        except Exception as exc:
            state.add_warning(projects_dir, str(exc))
            return list(state.warnings)

        # ── L1: project.json in parallel ────────────────────────────────
        def _load_project(name: str) -> str | None:
            project_dir = fs.join(projects_dir, name)
            meta = fs.join(project_dir, "project.json")
            ok = _safe_read(fs, meta, state, on_file=on_file) is not None
            if ok:
                _prefetch_concept_files(fs, project_dir, state, on_file=on_file)
                # Generic Folder mounts on the project (dirs carrying meta.json).
                _prefetch_meta_mounts(
                    fs,
                    project_dir,
                    state,
                    on_file=on_file,
                    skip={EXPERIMENT_CONTAINER, "assets", "cache"},
                )
            return name if ok else None

        healthy_projects = [
            n
            for n in _parallel_map(
                _load_project,
                project_names,
                prepare=lambda names: prime(
                    [fs.join(projects_dir, name, "project.json") for name in names]
                ),
                max_workers=workers,
                force_fetch_fs=force_fs,
            )
            if n
        ]

        # ── L1b: listdir experiments/ per project (parallel) ────────────
        def _list_experiments(project_name: str) -> list[tuple[str, str]]:
            project_dir = fs.join(projects_dir, project_name)
            experiments_dir = fs.join(project_dir, EXPERIMENT_CONTAINER)
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
            experiment_dir = fs.join(projects_dir, project_name, EXPERIMENT_CONTAINER, exp_name)
            meta = fs.join(experiment_dir, "experiment.json")
            ok = _safe_read(fs, meta, state, on_file=on_file) is not None
            if ok:
                _prefetch_concept_files(fs, experiment_dir, state, on_file=on_file)
                _prefetch_meta_mounts(
                    fs,
                    experiment_dir,
                    state,
                    on_file=on_file,
                    skip={RUN_CONTAINER, "assets", "cache"},
                )
            return pair if ok else None

        healthy_exps = [
            p
            for p in _parallel_map(
                _load_experiment,
                exp_pairs,
                prepare=lambda pairs: prime(
                    [
                        fs.join(projects_dir, p, EXPERIMENT_CONTAINER, e, "experiment.json")
                        for p, e in pairs
                    ]
                ),
                max_workers=workers,
                force_fetch_fs=force_fs,
            )
            if p
        ]

        # ── L2b: listdir runs/ per experiment (parallel) ────────────────
        def _list_runs(pair: tuple[str, str]) -> list[tuple[str, str, str]]:
            project_name, exp_name = pair
            experiment_dir = fs.join(projects_dir, project_name, EXPERIMENT_CONTAINER, exp_name)
            runs_dir = fs.join(experiment_dir, RUN_CONTAINER)
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

        def _load_run(triple: tuple[str, str, str]) -> list[str]:
            project_name, exp_name, run_name = triple
            run_dir = fs.join(
                projects_dir,
                project_name,
                EXPERIMENT_CONTAINER,
                exp_name,
                RUN_CONTAINER,
                run_name,
            )
            meta = fs.join(run_dir, "run.json")
            if _safe_read(fs, meta, state, on_file=on_file) is not None:
                _prefetch_concept_files(fs, run_dir, state, on_file=on_file)
                executions = fs.join(run_dir, "executions")
                try:
                    entries = fs.scandir(executions, with_stat=False)
                except FileNotFoundError:
                    return []
                except Exception as exc:
                    state.add_warning(executions, str(exc))
                    return []
                return [
                    fs.join(executions, entry.name, "execution.json")
                    for entry in entries
                    if entry.is_dir
                ]
            return []

        execution_paths = [
            path
            for paths in _parallel_map(
                _load_run,
                run_triples,
                max_workers=workers,
                force_fetch_fs=force_fs,
                prepare=lambda triples: prime(
                    [
                        fs.join(
                            projects_dir, p, EXPERIMENT_CONTAINER, e, RUN_CONTAINER, r, "run.json"
                        )
                        for p, e, r in triples
                    ]
                ),
            )
            for path in paths
        ]
        for start in range(0, len(execution_paths), 128):
            chunk = execution_paths[start : start + 128]
            prime(chunk)
            for path in chunk:
                _safe_read(fs, path, state, warn_on_missing=False, on_file=on_file)

    return list(state.warnings)


# Fixed container names. Declared execution directories are read at call time.
_META_MOUNT_FIXED = frozenset(
    {
        PROJECT_CONTAINER,
        EXPERIMENT_CONTAINER,
        RUN_CONTAINER,
        "assets",
        "cache",
        "executions",
        # legacy on-disk name: written by runs before D86 removed the agent layer; tolerated on read
        "plan",
        "source",
        # legacy on-disk name: written by runs before D86 removed the agent layer; tolerated on read
        "harness",
        "alive",
    }
)


def _meta_mount_skip() -> frozenset[str]:
    """Container names plus the execution directories registered right now."""
    return execution_dir_names() | _META_MOUNT_FIXED


def _prefetch_concept_files(
    fs: FileSystem,
    concept_dir: str,
    state: _PrefetchState,
    *,
    on_file: Callable[[str], None] | None = None,
) -> None:
    """Pull concept identity + narrative (``meta.json`` / ``index.md``)."""
    for name in ("meta.json", "index.md"):
        _safe_read(
            fs,
            fs.join(concept_dir, name),
            state,
            warn_on_missing=False,
            on_file=on_file,
        )


def _prefetch_meta_mounts(
    fs: FileSystem,
    parent_dir: str,
    state: _PrefetchState,
    *,
    on_file: Callable[[str], None] | None = None,
    skip: set[str] | frozenset[str] | None = None,
) -> None:
    """Prefetch ``meta.json`` / ``index.md`` Concept mounts under *parent_dir*.

    A mount (a directory at the project or experiment level) is a sibling dir
    carrying ``meta.json`` (plus ``index.md``). Without this, a pin-cached
    remote walk never sees those mounts and the tree stays empty.
    """
    skip_names = set(_meta_mount_skip())
    if skip:
        skip_names |= set(skip)
    try:
        names = list(fs.listdir(parent_dir))
    except FileNotFoundError:
        return
    except Exception as exc:
        state.add_warning(parent_dir, str(exc))
        return
    for name in names:
        if name in skip_names or name.startswith("."):
            continue
        child = fs.join(parent_dir, name)
        try:
            if not fs.is_dir(child):
                continue
        except Exception:
            continue
        _prefetch_concept_files(fs, child, state, on_file=on_file)


def _safe_read(
    fs: FileSystem,
    path: str,
    state: _PrefetchState,
    *,
    warn_on_missing: bool = True,
    on_file: Callable[[str], None] | None = None,
) -> str | None:
    try:
        if path in state.prefetched:
            value = state.prefetched.pop(path)
            if isinstance(value, Exception):
                raise value
            text = value.decode("utf-8")
        else:
            text = fs.read_text(path)
    except FileNotFoundError as exc:
        if warn_on_missing:
            state.add_warning(path, f"not found: {exc}")
        return None
    except Exception as exc:
        state.add_warning(path, str(exc))
        return None
    if on_file is not None:
        with contextlib.suppress(Exception):
            on_file(path)
    return text
