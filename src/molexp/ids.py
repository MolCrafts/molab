"""Identity primitives — slug / unique-id / content-hash, cross-layer.

Holds the pure, layer-agnostic helpers behind molexp's identity law:
uniqueness (:func:`generate_id` / :func:`generate_asset_id`),
reproducibility (:func:`compute_content_hash`), and slug derivation
(:func:`slugify`). They sit *above* ``molexp.workspace`` in the same
category as :mod:`molexp.path` and :mod:`molexp.atomicio` — citable from
any layer, including the OKF ``knowledge`` bottom layer, without importing
workspace.

This module must not import any molexp business layer; only stdlib is
permitted. ``molexp.workspace.utils`` re-exports these symbols as
back-compat aliases (same function objects). Run-domain id derivation
(``derive_run_id`` / ``derive_execution_id``) is deliberately NOT here —
it stays in ``molexp.workspace.utils``.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

_UUID7_LOCK = threading.Lock()
_UUID7_LAST_MS = -1
_UUID7_RANDOM = 0


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

    Python 3.12 is Molexp's supported floor and does not expose
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
    hasher = hashlib.new(algorithm)

    if path.is_dir():
        for entry in sorted(path.rglob("*")):
            if entry.is_file():
                rel = entry.relative_to(path).as_posix().encode()
                hasher.update(rel + b"\0")
                with open(entry, "rb") as f:  # noqa: PTH123
                    while chunk := f.read(8192):
                        hasher.update(chunk)
                hasher.update(b"\0")
    else:
        with open(path, "rb") as f:  # noqa: PTH123
            while chunk := f.read(8192):
                hasher.update(chunk)

    return f"{algorithm}:{hasher.hexdigest()}"


__all__ = [
    "compute_content_hash",
    "compute_definition_hash",
    "generate_asset_id",
    "generate_id",
    "generate_uuid7",
    "slugify",
]
