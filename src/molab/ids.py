"""Identity primitives — slug / unique-id / content-hash, cross-layer.

Holds the pure, layer-agnostic helpers behind molab's identity law:
uniqueness (:func:`generate_id` / :func:`generate_asset_id`),
reproducibility (:func:`compute_content_hash`), and slug derivation
(:func:`slugify`). They sit *above* ``molab.workspace`` in the same
category as :mod:`molab.path` and :mod:`molab.atomicio` — citable from
any layer, including the OKF ``knowledge`` bottom layer, without importing
workspace.

This module must not import any molab business layer; only stdlib is
permitted. ``molab.workspace.utils`` re-exports these symbols as
back-compat aliases (same function objects). Run-domain id derivation
(``derive_run_id`` / ``derive_execution_id``) is deliberately NOT here —
it stays in ``molab.workspace.utils``.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import threading
import time
from collections import OrderedDict
from pathlib import Path
from uuid import UUID, uuid4

_UUID7_LOCK = threading.Lock()
_UUID7_LAST_MS = -1
_UUID7_RANDOM = 0

_HASH_CHUNK = 1 << 20
"""Read size for streaming hashes.

The old 8 KiB made hashing syscall-bound: a 10 GB artifact cost ~1.3 M reads
for work ``hashlib`` does in microseconds. 1 MiB keeps the memory flat and
lets hashlib release the GIL for a useful span per chunk.
"""

_HASH_MEMO_MAX = 4096
_hash_memo: OrderedDict[tuple[str, str, int, int], str] = OrderedDict()
"""``(realpath, algorithm, size, mtime_ns) -> digest`` for files.

In-process only and keyed on the file's own identity, so a changed file can
never hit: this is a cache of the truth, not a second copy of it. Directories
are never memoized — their digest depends on a whole subtree, which a single
stat cannot validate.
"""


def slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a valid slug.

    Args:
        text: Input text.
        max_len: Maximum length.

    Returns:
        Slugified string: lowercased, spaces/underscores → hyphens,
        non-alphanumerics dropped, collapsed hyphens, truncated.
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove non-alphanumeric characters except hyphens
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Truncate to max length
    return slug[:max_len]


def generate_id() -> str:
    """Generate a unique 8-character hex id.

    Returns:
        8-character hex string, e.g., ``'a3f2e8d9'``.
    """
    return uuid4().hex[:8]


def generate_asset_id() -> str:
    """Generate a unique asset id using UUID.

    Returns:
        UUID string, e.g., ``'a3f2e8d9-4b1c-4e5f-9a2b-1c3d4e5f6a7b'``.
    """
    return str(uuid4())


def generate_uuid7() -> str:
    """Generate a time-ordered RFC 9562 UUIDv7 string.

    Python 3.12 is Molab's supported floor and does not expose
    :func:`uuid.uuid7`, so the small generator lives here instead of adding a
    runtime dependency. Calls within one millisecond increment the 74-bit
    random field, which preserves ordering and prevents same-process
    collisions; different processes retain 74 bits of randomness.
    """
    global _UUID7_LAST_MS, _UUID7_RANDOM

    with _UUID7_LOCK:
        now_ms = int(time.time_ns() // 1_000_000)
        if now_ms > _UUID7_LAST_MS:
            _UUID7_LAST_MS = now_ms
            _UUID7_RANDOM = secrets.randbits(74)
        else:
            now_ms = _UUID7_LAST_MS
            _UUID7_RANDOM = (_UUID7_RANDOM + 1) & ((1 << 74) - 1)

        rand_a = _UUID7_RANDOM >> 62
        rand_b = _UUID7_RANDOM & ((1 << 62) - 1)
        value = (now_ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(UUID(int=value))


def compute_definition_hash(value: object) -> str:
    """Hash canonical JSON separately from an entity's UUID identity."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def compute_content_hash(path: Path, algorithm: str = "sha256") -> str:
    """Compute hash of a file's bytes or a directory tree.

    For files, returns the digest of the byte stream. For directories,
    walks every contained file in sorted-relative-path order and hashes
    ``relpath\\0bytes\\0`` per file, so the result is invariant to
    filesystem walk order but sensitive to filenames.

    Args:
        path: File or directory to hash.
        algorithm: Hash algorithm name (default: ``sha256``).

    Returns:
        Hash string with algorithm prefix, e.g., ``"sha256:a3b4c5d6..."``.
    """
    if path.is_dir():
        # The digest is an artifact *address*, so the byte stream fed to the
        # hasher must stay exactly what it has always been: `relpath\0` then
        # the file's raw bytes then `\0`. (Chunk size is free to change — the
        # hash is over the stream, not the reads.) That also rules out
        # memoizing per file here: substituting a per-file digest would change
        # every directory hash ever stored.
        hasher = hashlib.new(algorithm)
        for entry in sorted(path.rglob("*")):
            if entry.is_file():
                rel = entry.relative_to(path).as_posix().encode()
                hasher.update(rel + b"\0")
                with open(entry, "rb") as f:  # noqa: PTH123
                    while chunk := f.read(_HASH_CHUNK):
                        hasher.update(chunk)
                hasher.update(b"\0")
        return f"{algorithm}:{hasher.hexdigest()}"

    return f"{algorithm}:{_file_digest(path, algorithm)}"


def _memo_key(path: Path, algorithm: str) -> tuple[str, str, int, int] | None:
    """Identity of *path*'s current contents, or ``None`` if it cannot be taken."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path.resolve()), algorithm, st.st_size, st.st_mtime_ns)


def _file_digest(path: Path, algorithm: str) -> str:
    """Hex digest of a file's bytes, memoized on ``(path, size, mtime_ns)``."""
    key = _memo_key(path, algorithm)
    if key is not None:
        cached = _hash_memo.get(key)
        if cached is not None:
            _hash_memo.move_to_end(key)
            return cached

    hasher = hashlib.new(algorithm)
    with open(path, "rb") as fh:  # noqa: PTH123
        while chunk := fh.read(_HASH_CHUNK):
            hasher.update(chunk)
    digest = hasher.hexdigest()

    if key is not None:
        _hash_memo[key] = digest
        _hash_memo.move_to_end(key)
        while len(_hash_memo) > _HASH_MEMO_MAX:
            _hash_memo.popitem(last=False)
    return digest


def hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
    """Hash an in-memory payload with the same spelling as a file hash.

    Lets a caller that already holds the bytes it just wrote address them
    without reading the file back.

    Args:
        data: The payload.
        algorithm: Hash algorithm name.

    Returns:
        ``"<algorithm>:<hexdigest>"``.
    """
    return f"{algorithm}:{hashlib.new(algorithm, data).hexdigest()}"


def hash_copy(src: Path, dst: Path, *, algorithm: str = "sha256") -> str:
    """Copy *src* to *dst* and return its content hash — in one read pass.

    Registering an artifact means copying it and addressing it. Done
    separately that reads a multi-gigabyte file twice, and the second pass is
    pure waste: the bytes were already in hand during the copy.

    Metadata is copied as ``shutil.copy2`` would, and the digest is memoized
    against *dst* so an immediate re-hash of the destination is free.

    Args:
        src: File to copy.
        dst: Destination path; parent directories are created.
        algorithm: Hash algorithm name.

    Returns:
        ``"<algorithm>:<hexdigest>"`` of the copied bytes.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.new(algorithm)
    with open(src, "rb") as fin, open(dst, "wb") as fout:  # noqa: PTH123
        while chunk := fin.read(_HASH_CHUNK):
            hasher.update(chunk)
            fout.write(chunk)
    shutil.copystat(src, dst)
    digest = hasher.hexdigest()

    key = _memo_key(dst, algorithm)
    if key is not None:
        _hash_memo[key] = digest
        _hash_memo.move_to_end(key)
        while len(_hash_memo) > _HASH_MEMO_MAX:
            _hash_memo.popitem(last=False)
    return f"{algorithm}:{digest}"


def clear_hash_memo() -> None:
    """Drop the content-hash memo (tests only)."""
    _hash_memo.clear()


__all__ = [
    "clear_hash_memo",
    "compute_content_hash",
    "compute_definition_hash",
    "generate_asset_id",
    "generate_id",
    "generate_uuid7",
    "hash_bytes",
    "hash_copy",
    "slugify",
]
