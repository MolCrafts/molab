"""Filesystem-class detection and the policies that depend on it.

The same code runs against three very different filesystems, and the right
behaviour differs on each:

* **local-fast** — a local disk. Metadata calls are cheap, ``flock`` works,
  SQLite WAL works.
* **network-local** — NFS / Lustre / GPFS mounted on this host. Every ``stat``
  is a network round-trip, ``flock`` may be unsupported (Lustre without
  ``-o flock`` fails ``ENOSYS``, which the caller must not mistake for
  contention), and WAL's shared-memory file is unsafe.
* **remote-ssh** — reached through a molq transport. Every call is an SSH
  round-trip, so listings must be batched and cached aggressively; advisory
  locks and a local SQLite event log are not meaningful at all.

Detection is one read of ``/proc/self/mounts`` per process, cached per
resolved path. ``os.statvfs`` is deliberately not used: it reports no
filesystem type on Linux or macOS.

Stdlib only — layer 0.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .base import PathArg

LockBackend = Literal["flock", "o_excl", "none"]
"""Which advisory-lock mechanism a filesystem can actually honour."""

SqliteJournal = Literal["WAL", "DELETE"]
"""SQLite journal mode; WAL needs a shared-memory file the mount must support."""

ENV_OVERRIDE = "MOLAB_FS_PROFILE"
"""Set to a :class:`FsKind` value to force detection (escape hatch + tests)."""


class FsKind(StrEnum):
    """The three filesystem classes molab behaves differently on."""

    LOCAL_FAST = "local-fast"
    NETWORK_LOCAL = "network-local"
    REMOTE_SSH = "remote-ssh"


NETWORK_FSTYPES: frozenset[str] = frozenset(
    {
        "9p",
        "afs",
        "beegfs",
        "ceph",
        "cifs",
        "fuse.glusterfs",
        "fuse.sshfs",
        "glusterfs",
        "gpfs",
        "lustre",
        "nfs",
        "nfs4",
        "panfs",
        "smb3",
        "smbfs",
        "virtiofs",
    }
)
"""Mount types whose metadata calls cross a network and whose locks are suspect."""


@dataclass(frozen=True, slots=True)
class FsProfile:
    """What a filesystem's class implies for the policies that depend on it.

    Attributes:
        kind: The detected class.
        fstype: Mount type when known (``"lustre"``, ``"ext4"``, …).
        locks: Lock backend :func:`molab.atomicio.file_lock` should use.
        sqlite_journal: Journal mode for SQLite databases on this filesystem.
        prefetch_workers: Parallelism for bulk index prefetches.
        scandir_with_stat: Whether container walks should ask for per-entry
            metadata; on a network mount the extra stats are round-trips that
            a walk looking only for directories does not need.
    """

    kind: FsKind
    fstype: str | None = None
    locks: LockBackend = "flock"
    sqlite_journal: SqliteJournal = "WAL"
    prefetch_workers: int = 1
    scandir_with_stat: bool = True


LOCAL_FAST_PROFILE = FsProfile(
    kind=FsKind.LOCAL_FAST,
    locks="flock",
    sqlite_journal="WAL",
    prefetch_workers=1,
    scandir_with_stat=True,
)

NETWORK_LOCAL_PROFILE = FsProfile(
    kind=FsKind.NETWORK_LOCAL,
    locks="o_excl",
    sqlite_journal="DELETE",
    prefetch_workers=8,
    scandir_with_stat=False,
)

REMOTE_SSH_PROFILE = FsProfile(
    kind=FsKind.REMOTE_SSH,
    locks="none",
    sqlite_journal="DELETE",
    prefetch_workers=8,
    scandir_with_stat=True,
)

_BY_KIND: dict[FsKind, FsProfile] = {
    FsKind.LOCAL_FAST: LOCAL_FAST_PROFILE,
    FsKind.NETWORK_LOCAL: NETWORK_LOCAL_PROFILE,
    FsKind.REMOTE_SSH: REMOTE_SSH_PROFILE,
}

_MOUNTS_PATH = "/proc/self/mounts"

# (mount point, fstype) sorted longest-mount-point-first; None until first read.
_mounts_cache: list[tuple[str, str]] | None = None
_profile_cache: dict[str, FsProfile] = {}


def profile_for_kind(kind: FsKind) -> FsProfile:
    """Return the canonical profile constant for *kind*."""
    return _BY_KIND[kind]


def _read_mounts() -> list[tuple[str, str]]:
    """Parse ``/proc/self/mounts`` once per process, longest mount point first."""
    global _mounts_cache
    if _mounts_cache is not None:
        return _mounts_cache
    entries: list[tuple[str, str]] = []
    try:
        with open(_MOUNTS_PATH, encoding="utf-8", errors="replace") as fh:  # noqa: PTH123
            for line in fh:
                fields = line.split()
                if len(fields) < 3:
                    continue
                # Mount points are escaped octal-style for spaces etc.
                point = fields[1].replace("\\040", " ").replace("\\011", "\t")
                entries.append((point, fields[2]))
    except OSError:
        entries = []
    entries.sort(key=lambda kv: len(kv[0]), reverse=True)
    _mounts_cache = entries
    return entries


def _fstype_for(path: str) -> str | None:
    """Longest-prefix mount lookup for an absolute, resolved *path*."""
    for point, fstype in _read_mounts():
        if path == point or path.startswith(point.rstrip("/") + "/") or point == "/":
            return fstype
    return None


def detect_fs_profile(path: PathArg) -> FsProfile:
    """Classify the filesystem holding *path* and return its policy profile.

    ``MOLAB_FS_PROFILE`` overrides detection entirely. Otherwise the mount
    table decides; anything not in :data:`NETWORK_FSTYPES` (and any platform
    without ``/proc``) is treated as local-fast, which is the conservative
    choice — it keeps ``flock`` and WAL, both of which degrade loudly rather
    than silently if that guess is wrong.

    Args:
        path: Any path on the filesystem in question; need not exist.

    Returns:
        The :class:`FsProfile` for that filesystem. Results are cached per
        resolved path for the life of the process.
    """
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        try:
            return profile_for_kind(FsKind(override))
        except ValueError:
            pass  # Unknown value — fall through to real detection.

    key = os.path.realpath(os.fspath(path))
    cached = _profile_cache.get(key)
    if cached is not None:
        return cached

    fstype = _fstype_for(key)
    if fstype is not None and fstype in NETWORK_FSTYPES:
        profile = FsProfile(
            kind=FsKind.NETWORK_LOCAL,
            fstype=fstype,
            locks=NETWORK_LOCAL_PROFILE.locks,
            sqlite_journal=NETWORK_LOCAL_PROFILE.sqlite_journal,
            prefetch_workers=NETWORK_LOCAL_PROFILE.prefetch_workers,
            scandir_with_stat=NETWORK_LOCAL_PROFILE.scandir_with_stat,
        )
    else:
        profile = FsProfile(
            kind=FsKind.LOCAL_FAST,
            fstype=fstype,
            locks=LOCAL_FAST_PROFILE.locks,
            sqlite_journal=LOCAL_FAST_PROFILE.sqlite_journal,
            prefetch_workers=LOCAL_FAST_PROFILE.prefetch_workers,
            scandir_with_stat=LOCAL_FAST_PROFILE.scandir_with_stat,
        )
    _profile_cache[key] = profile
    return profile


def reset_profile_cache() -> None:
    """Drop the memoized mount table and profiles (tests only)."""
    global _mounts_cache
    _mounts_cache = None
    _profile_cache.clear()


__all__ = [
    "ENV_OVERRIDE",
    "LOCAL_FAST_PROFILE",
    "NETWORK_FSTYPES",
    "NETWORK_LOCAL_PROFILE",
    "REMOTE_SSH_PROFILE",
    "FsKind",
    "FsProfile",
    "LockBackend",
    "SqliteJournal",
    "detect_fs_profile",
    "profile_for_kind",
    "reset_profile_cache",
]
