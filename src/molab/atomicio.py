"""Atomic persistence primitives — cross-layer, citable from any layer.

Holds the canonical atomic write helpers (temp-file + ``os.replace``) and
the advisory inter-process file lock. These sit *above* ``molab.workspace``
in the same category as :mod:`molab.path` — a cross-layer primitive that
the bottom storage layers (``workspace`` and the OKF ``knowledge`` layer)
both cite without depending on each other.

This module must not import any molab business layer; only stdlib and the
root-level ``mollog`` logger are permitted.

``molab.workspace.base`` / ``molab.workspace._file_lock`` re-export these
symbols as back-compat aliases (same function objects), so existing call
sites keep working unchanged.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import Literal

from mollog import get_logger

try:  # pragma: no cover - platform-dependent import
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX platforms
    _HAS_FCNTL = False

logger = get_logger(__name__)

# How long a writer waits for a contended lock before failing loudly.
DEFAULT_LOCK_TIMEOUT_SECONDS = 10.0
# Poll cadence while waiting for a contended lock.
_POLL_INTERVAL_SECONDS = 0.02

LockBackend = Literal["flock", "o_excl", "none"]
"""Which lock mechanism to use; see :func:`file_lock`."""

# Errnos that mean "someone else holds it" — the only ones worth waiting on.
_CONTENDED_ERRNOS = frozenset({errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES})
# Errnos that mean "this filesystem does not do flock" — waiting is pointless.
_UNSUPPORTED_ERRNOS = frozenset({errno.ENOLCK, errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL})

# One warning per process per lock backend downgrade; a per-call warning would
# fire on every metadata write.
_warned_unsupported = False


def _stringify_with_warning(value: object) -> str:
    """``json.dumps`` fallback: stringify non-JSON values LOUDLY, never silently.

    Callers should hand this function JSON-safe data (pydantic
    ``model_dump(mode="json")``, sanitized outputs); when they don't, the
    value is still persisted as its ``str()`` so a write never corrupts a
    run mid-flight — but the offender is named in the log instead of being
    silently masked.
    """
    logger.warning(
        f"atomic_write_json: non-JSON value of type {type(value).__name__} "
        f"stringified on write — pass JSON-safe data (e.g. model_dump(mode='json'))."
    )
    return str(value)


def dump_canonical_json(data: object) -> str:
    """Serialize *data* in molab's ONE canonical JSON form.

    ``indent=2, sort_keys=True, ensure_ascii=False`` + trailing newline —
    the single byte format shared by every atomic JSON writer (entity files,
    workflow-state checkpoints, run artifacts), so derived views such as
    the git checkpoint projection re-derive byte-identical content.
    """
    return (
        json.dumps(
            data, indent=2, ensure_ascii=False, sort_keys=True, default=_stringify_with_warning
        )
        + "\n"
    )


def atomic_write_json(path: Path, data: object) -> None:
    """Write JSON data to a file atomically via write-to-temp + rename.

    On POSIX systems, os.replace is atomic — if the process crashes
    mid-write, the original file remains intact. This prevents data
    corruption for critical files like run.json, metadata files, and
    workflow-state checkpoints. Serialization goes through
    :func:`dump_canonical_json` (the one canonical byte form); the temp file
    is chmod'd ``0o600`` before the rename, matching the workspace entity
    writer.

    Args:
        path: Destination file path.
        data: JSON-serializable value (non-JSON leaves are stringified with
            a loud warning — see :func:`dump_canonical_json`).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file in the same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=f".{path.stem}_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dump_canonical_json(data))
        os.chmod(tmp_path, 0o600)  # noqa: PTH101
        os.replace(tmp_path, path)  # noqa: PTH105
    except BaseException:
        # Clean up temp file on any failure (including KeyboardInterrupt)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)  # noqa: PTH108
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write bytes atomically via write-to-temp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=f".{path.stem}_")
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        tmp.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text to a file atomically via write-to-temp + rename.

    Companion to :func:`atomic_write_json` for plain-text artifacts —
    markdown reports, generated source previews, log snapshots, and OKF
    ``meta.json`` / ``index.md`` / ``log.md`` files — that are read back
    as strings rather than parsed as JSON. Same temp-file + ``os.replace``
    pattern; if the process crashes mid-write the original file remains
    intact.

    Args:
        path: Destination file path.
        content: Text to write.
        encoding: Text encoding (default ``"utf-8"``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=f".{path.stem}_")
    tmp = Path(tmp_path)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        tmp.replace(path)
    except BaseException:
        # Clean up temp file on any failure (including KeyboardInterrupt).
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


class FileLockTimeoutError(TimeoutError):
    """Raised when an advisory file lock cannot be acquired in time."""


@contextlib.contextmanager
def _o_excl_lock(lock_path: Path, timeout: float) -> Generator[None]:
    """Lock by exclusive file *creation* — the portable fallback.

    ``O_CREAT | O_EXCL`` is atomic even on NFS, which is why it is the
    fallback where ``flock`` is unavailable or lies. The cost is that a
    process killed mid-section leaves the file behind, so a lock older than
    ``3 x timeout`` is treated as abandoned and broken — long enough that a
    live holder is never evicted, short enough that a crash does not wedge the
    workspace forever.
    """
    marker = lock_path.with_suffix(lock_path.suffix + ".excl")
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while True:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
            break
        except FileExistsError:
            try:
                age = time.time() - marker.stat().st_mtime
            except OSError:
                age = 0.0
            if age > 3 * timeout:
                logger.warning(f"file_lock: breaking stale lock {marker} (age {age:.0f}s)")
                with contextlib.suppress(OSError):
                    marker.unlink()
                continue
            if time.monotonic() >= deadline:
                raise FileLockTimeoutError(
                    f"could not acquire advisory lock {marker} within "
                    f"{timeout:.1f}s — another molab process is holding it"
                ) from None
            time.sleep(_POLL_INTERVAL_SECONDS)
        except OSError:
            logger.debug(f"file_lock: cannot create {marker}; proceeding without lock")
            yield
            return
    try:
        yield
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            marker.unlink()


@contextlib.contextmanager
def file_lock(
    lock_path: Path,
    *,
    timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    backend: LockBackend = "flock",
) -> Generator[None]:
    """Hold an exclusive advisory lock on *lock_path* for the ``with`` body.

    Serializes read-modify-write cycles on a JSON file written by several
    uncoordinated processes (server, foreground CLI, detached workers).
    Each write is atomic, but an RMW without a lock can still drop a
    concurrent update — this lock closes that window.

    The sidecar lock file is created on demand (never deleted under the
    ``flock`` backend — deleting a lock file open in another process would
    break ``flock`` semantics).

    Backends:

    * ``"flock"`` (default) — ``fcntl.flock`` on a sidecar. Correct and
      self-releasing on crash, but not honoured by every filesystem.
    * ``"o_excl"`` — exclusive file creation; for mounts where ``flock`` is
      unsupported (Lustre without ``-o flock``, some NFS setups).
    * ``"none"`` — no locking, for filesystems where neither is meaningful
      (a remote tree reached over SSH).

    ``"flock"`` degrades to ``"o_excl"`` by itself when the kernel reports the
    operation unsupported. That distinction is the point: the previous version
    treated *every* ``OSError`` as contention, so on a Lustre mount without
    ``-o flock`` each metadata write spun for the full timeout and then raised
    a "another molab process is holding it" error that named a conflict which
    did not exist.

    Args:
        lock_path: Sidecar lock-file path (e.g. ``run.json.lock``).
        timeout: Seconds to wait for a contended lock.
        backend: Lock mechanism; see above.

    Raises:
        FileLockTimeoutError: The lock stayed contended past *timeout*.
    """
    global _warned_unsupported

    if backend == "none":
        yield
        return
    if backend == "o_excl":
        with _o_excl_lock(lock_path, timeout):
            yield
        return
    if not _HAS_FCNTL:
        logger.debug(f"file_lock: fcntl unavailable; proceeding without lock for {lock_path}")
        yield
        return

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        logger.debug(
            f"file_lock: cannot create {lock_path}; proceeding without lock", exc_info=True
        )
        yield
        return

    unsupported = False
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno in _UNSUPPORTED_ERRNOS:
                    # This filesystem does not implement flock — waiting would
                    # burn the whole timeout and then raise a false conflict.
                    if not _warned_unsupported:
                        _warned_unsupported = True
                        logger.warning(
                            f"file_lock: flock unsupported on this filesystem "
                            f"({errno.errorcode.get(exc.errno, exc.errno)}); "
                            f"falling back to exclusive-create locks"
                        )
                    unsupported = True
                    break
                if exc.errno is not None and exc.errno not in _CONTENDED_ERRNOS:
                    raise
                if time.monotonic() >= deadline:
                    raise FileLockTimeoutError(
                        f"could not acquire advisory lock {lock_path} within "
                        f"{timeout:.1f}s — another molab process is holding it"
                    ) from None
                time.sleep(_POLL_INTERVAL_SECONDS)
    except BaseException:
        os.close(fd)
        raise

    if unsupported:
        os.close(fd)
        with _o_excl_lock(lock_path, timeout):
            yield
        return

    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "FileLockTimeoutError",
    "LockBackend",
    "atomic_write_json",
    "atomic_write_text",
    "file_lock",
]
