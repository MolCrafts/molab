"""Directory names a human can read.

A workspace path is navigated by people — with ``ls``, with tab completion,
in a paper's methods section. So the path is a *name*, not an identity: an
Experiment directory is its slug, a Run directory is its parameters, an
Execution directory is its attempt number.

Identity stays where identity belongs: the UUIDv7 in the entity JSON's
``id`` field, which history and cross-entity references cite. Renaming a
directory therefore never breaks a reference, and reading a directory
listing tells you what was actually run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from molexp.ids import slugify

if TYPE_CHECKING:
    from molexp._typing import JSONValue

MAX_RUN_SLUG = 96
"""Beyond this a name stops helping; the tail becomes a hash."""

_UNSAFE = re.compile(r"[^A-Za-z0-9._=+-]+")
_COLLAPSE = re.compile(r"_{2,}")


def workspace_root(path: Path) -> Path | None:
    """Walk up from *path* to the directory holding ``workspace.json``.

    Artifact paths are workspace-relative, so anything that resolves one back
    to bytes needs the root — and only the tree knows where it is.
    """
    for candidate in (path, *path.parents):
        if (candidate / "workspace.json").is_file():
            return candidate
    return None


def entity_slug(name: str, *, fallback: str) -> str:
    """Directory name for a Project / Experiment: its human name, slugified."""
    slug = slugify(name)
    return slug or _short(fallback)


def execution_slug(seq: int) -> str:
    """Directory name for one attempt: ``e01``, ``e02``, … — time-ordered by eye."""
    if seq < 1:
        raise ValueError(f"execution sequence starts at 1, got {seq}")
    return f"e{seq:02d}"


def parse_execution_seq(slug: str) -> int | None:
    """Recover the attempt number from an execution directory name."""
    match = re.fullmatch(r"e(\d+)", slug)
    return int(match.group(1)) if match else None


def run_slug(params: dict[str, JSONValue] | None, *, fallback: str) -> str:
    """Directory name for a Run: its parameters, ``key=value`` joined by ``_``.

    Keys are sorted so the same cell of a sweep always lands on the same
    name. An empty or unrenderable parameter set, or one that overflows
    :data:`MAX_RUN_SLUG`, falls back to a short digest of *fallback* (the
    run's ``definition_hash``) — never to a UUID, which would tell a reader
    nothing at all.
    """
    if not params:
        return _short(fallback)
    parts = [f"{_token(key)}={_token(value)}" for key, value in sorted(params.items())]
    slug = _COLLAPSE.sub("_", "_".join(part for part in parts if part))
    slug = slug.strip("_")
    if not slug:
        return _short(fallback)
    if len(slug) > MAX_RUN_SLUG:
        keep = MAX_RUN_SLUG - 9
        slug = f"{slug[:keep].rstrip('_')}_{_short(fallback)}"
    return slug


def disambiguate(slug: str, taken: set[str]) -> str:
    """Return *slug*, or the first ``slug-2`` / ``slug-3`` … that is free."""
    if slug not in taken:
        return slug
    for suffix in range(2, 1000):
        candidate = f"{slug}-{suffix}"
        if candidate not in taken:
            return candidate
    raise ValueError(f"cannot disambiguate {slug!r}: 999 siblings already taken")


def _token(value: object) -> str:
    if isinstance(value, bool):
        text = "yes" if value else "no"
    elif isinstance(value, float):
        text = f"{value:g}"
    elif isinstance(value, (list, tuple)):
        text = "-".join(_token(item) for item in value)
    elif isinstance(value, dict):
        text = "-".join(f"{_token(k)}{_token(v)}" for k, v in sorted(value.items()))
    else:
        text = str(value)
    return _UNSAFE.sub("-", text).strip("-_")


def _short(fallback: str) -> str:
    """Eight stable hex characters from a ``sha256:…`` hash or any string."""
    bare = fallback.rsplit(":", 1)[-1] if fallback else ""
    cleaned = re.sub(r"[^0-9a-f]", "", bare.lower())
    if len(cleaned) >= 8:
        return cleaned[:8]
    import hashlib

    return hashlib.sha256((fallback or "molexp").encode()).hexdigest()[:8]


__all__ = [
    "MAX_RUN_SLUG",
    "disambiguate",
    "entity_slug",
    "execution_slug",
    "parse_execution_seq",
    "run_slug",
    "workspace_root",
]
