"""Read and replace a document's structured record as one unit.

The record of a document is its frontmatter minus the keys every document
carries (:data:`COMMON_KEYS`). Classes that own a structured record — a
:class:`~molab.knowledge.concepts.Delegation`, or a planning document whose
role stores fields (Roadmap / Todo / Milestone) — can have it replaced whole.
The caller passes the digest it read; a changed file is a conflict, not a
silent overwrite.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .concept import Concept

__all__ = [
    "COMMON_KEYS",
    "RecordConflictError",
    "digest_of",
    "has_record",
    "record_of",
    "replace_record",
]

#: Frontmatter keys every document carries; never part of a structured record.
COMMON_KEYS: frozenset[str] = frozenset(
    {"class", "name", "created_by", "created_at", "tags", "status"}
)

_RECORD_ROLES = frozenset({"roadmap", "todo", "milestone"})


class RecordConflictError(Exception):
    """The document changed since the digest the caller read."""


def has_record(doc: Concept) -> bool:
    """Whether *doc*'s class owns a replaceable structured record."""
    klass = type(doc)
    return callable(getattr(klass, "check_record", None)) or (
        getattr(klass, "PLANNING_ROLE", None) in _RECORD_ROLES
    )


def digest_of(doc: Concept) -> str:
    """The sha256 of *doc*'s file bytes (``""`` when it does not exist)."""
    from .concept import read_text_or_none

    text = read_text_or_none(doc.path, fs=doc.fs)
    if text is None:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _common_keys(klass: type) -> frozenset[str]:
    """The common keys this class does not own. A Milestone's ``status`` is its record's."""
    if getattr(klass, "PLANNING_ROLE", None) == "milestone":
        return COMMON_KEYS - {"status"}
    return COMMON_KEYS


def record_of(doc: Concept) -> dict[str, object]:
    """*doc*'s structured record: its frontmatter without the common keys it does not own."""
    common = _common_keys(type(doc))
    return {key: value for key, value in doc.frontmatter().items() if key not in common}


def replace_record(
    doc: Concept,
    record: Mapping[str, object],
    *,
    if_match: str | None = None,
    body: str | None = None,
) -> str:
    """Replace *doc*'s structured record whole, and optionally its narrative.

    Keys of the old record that *record* omits are removed. The common keys
    are kept. The new record is validated by the class before anything is
    written.

    Args:
        doc: An existing document whose class owns a record.
        record: The complete new record. Common keys in it are ignored.
        if_match: The digest the caller read; ``None`` skips the check.
        body: A new narrative, or ``None`` to keep the current one.

    Returns:
        The new digest.

    Raises:
        TypeError: The class owns no structured record.
        FileNotFoundError: The document does not exist.
        RecordConflictError: *if_match* differs from the current digest.
        ValueError: The class rejects the record.
    """
    from .frontmatter import dump_frontmatter
    from .planning import check_planning_record
    from .worker_report import check_worker_record

    klass = type(doc)
    if not has_record(doc):
        raise TypeError(f"{klass.__name__} has no structured record to replace")
    if not doc.exists():
        raise FileNotFoundError(str(doc.path))
    if if_match is not None and digest_of(doc) != if_match:
        raise RecordConflictError(f"{doc.path} changed since it was read")
    owned_common = _common_keys(klass)
    clean = {str(key): value for key, value in record.items() if key not in owned_common}
    check_record = getattr(klass, "check_record", None)
    if check_record is not None:
        check_record(clean, existing={})
    check_planning_record(klass, clean, creating=True)
    check_worker_record(klass, clean, existing=None)
    common = {key: value for key, value in doc.frontmatter().items() if key in owned_common}
    narrative = doc.read() if body is None else body
    doc.write(
        dump_frontmatter({**common, **clean, "class": klass.__name__}, narrative, path=doc.path),
        replace=True,
    )
    return digest_of(doc)
