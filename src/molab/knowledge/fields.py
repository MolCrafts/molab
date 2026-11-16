"""A document's own fields: the frontmatter keys its class declares in ``FIELDS``.

Every document carries :data:`COMMON_KEYS`. Any other frontmatter key belongs
to the class: :attr:`~molab.knowledge.concept.Concept.FIELDS` declares them
(a pydantic model that refuses an unknown key), and ``None`` declares none.
There is no second schema. A write is checked against the class
(:func:`check_fields`), ``molab validate`` reports a file that breaks it, and
:func:`replace_fields` swaps a document's own fields whole. The caller passes
the digest it read; a changed file is a conflict, not a silent overwrite.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .concept import Concept

__all__ = [
    "COMMON_KEYS",
    "DigestConflictError",
    "check_fields",
    "digest_of",
    "own_fields",
    "replace_fields",
]

#: Frontmatter keys every document carries; never a class's own field.
COMMON_KEYS: frozenset[str] = frozenset({"class", "name", "created_by", "created_at", "tags"})


class DigestConflictError(Exception):
    """The document changed since the digest the caller read."""


def own_fields(meta: Mapping[str, object]) -> dict[str, object]:
    """*meta* without the common keys: what the class must declare."""
    return {str(key): value for key, value in meta.items() if key not in COMMON_KEYS}


def check_fields(klass: type[Concept], fields: Mapping[str, object]) -> None:
    """Refuse *fields* unless *klass* declares every key and accepts every value.

    Raises:
        ValueError: A key *klass* does not declare (a class with ``FIELDS =
            None`` declares none), or a value its model rejects. A pydantic
            ``ValidationError`` is a ``ValueError``.
    """
    model = klass.FIELDS
    if model is None:
        if fields:
            raise ValueError(
                f"{klass.__name__} declares no fields; got {', '.join(sorted(fields))}"
            )
        return
    model.model_validate(dict(fields))


def digest_of(doc: Concept) -> str:
    """The sha256 of *doc*'s file bytes (``""`` when it does not exist)."""
    from .concept import read_text_or_none

    text = read_text_or_none(doc.path, fs=doc.fs)
    if text is None:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_fields(
    doc: Concept,
    fields: Mapping[str, object],
    *,
    if_match: str | None = None,
    body: str | None = None,
) -> str:
    """Replace *doc*'s own fields whole, and optionally its narrative.

    A key of the old fields that *fields* omits is removed, so this is also
    how a stray key a hand edit left is cleared. The common keys are kept.
    The class checks the new fields before anything is written.

    Args:
        doc: An existing document.
        fields: The complete new fields; no common key.
        if_match: The digest the caller read; ``None`` skips the check.
        body: A new narrative, or ``None`` to keep the current one.

    Returns:
        The new digest.

    Raises:
        FileNotFoundError: The document does not exist.
        DigestConflictError: *if_match* differs from the current digest.
        ValueError: The class rejects *fields*.

    The digest check and the write run under the document's lock, and the
    change is one ``knowledge.fields_replaced`` history commit
    (:func:`~molab.knowledge.mutation.mutation`).
    """
    from .frontmatter import dump_frontmatter
    from .mutation import mutation

    klass = type(doc)
    if not doc.exists():
        raise FileNotFoundError(str(doc.path))
    with mutation(doc, "knowledge.fields_replaced", f"replace fields of {doc.name}"):
        if if_match is not None and digest_of(doc) != if_match:
            raise DigestConflictError(f"{doc.path} changed since it was read")
        check_fields(klass, fields)
        common = {key: value for key, value in doc.frontmatter().items() if key in COMMON_KEYS}
        narrative = doc.read() if body is None else body
        doc.write(
            dump_frontmatter(
                {**common, **fields, "class": klass.__name__}, narrative, path=doc.path
            ),
            replace=True,
        )
        return digest_of(doc)
