"""Read and replace a document's structured record as one unit.

The record of a document is its frontmatter minus the keys every document
carries (:data:`COMMON_KEYS`). A class that owns a structured record (one
that defines ``check_record``, such as
:class:`~molab.knowledge.concepts.Hypothesis`) can have it replaced whole.
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


class RecordConflictError(Exception):
    """The document changed since the digest the caller read."""


def has_record(doc: Concept) -> bool:
    """Whether *doc*'s class owns a replaceable structured record."""
    return callable(getattr(type(doc), "check_record", None))


def digest_of(doc: Concept) -> str:
    """The sha256 of *doc*'s file bytes (``""`` when it does not exist)."""
    from .concept import read_text_or_none

    text = read_text_or_none(doc.path, fs=doc.fs)
    if text is None:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_of(doc: Concept) -> dict[str, object]:
    """*doc*'s structured record: its frontmatter without the common keys."""
    return {key: value for key, value in doc.frontmatter().items() if key not in COMMON_KEYS}


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

    The digest check and the write run under the document's lock, and the
    change is one ``knowledge.record_replaced`` history commit
    (:func:`~molab.knowledge.mutation.mutation`).
    """
    from .frontmatter import dump_frontmatter
    from .mutation import mutation

    klass = type(doc)
    if not has_record(doc):
        raise TypeError(f"{klass.__name__} has no structured record to replace")
    if not doc.exists():
        raise FileNotFoundError(str(doc.path))
    with mutation(doc, "knowledge.record_replaced", f"replace record of {doc.name}"):
        if if_match is not None and digest_of(doc) != if_match:
            raise RecordConflictError(f"{doc.path} changed since it was read")
        clean = {str(key): value for key, value in record.items() if key not in COMMON_KEYS}
        check_record = getattr(klass, "check_record", None)
        if check_record is not None:
            check_record(clean, existing={})
        common = {key: value for key, value in doc.frontmatter().items() if key in COMMON_KEYS}
        narrative = doc.read() if body is None else body
        doc.write(
            dump_frontmatter(
                {**common, **clean, "class": klass.__name__}, narrative, path=doc.path
            ),
            replace=True,
        )
        return digest_of(doc)
