"""``ReferenceMeta`` — the bibliographic fields of a :class:`~molab.knowledge.concepts.Literature`.

They live in the document's frontmatter beside the keys every document
carries; the narrative holds the citation text. A PDF is pointed at
(``pdf_path`` / ``pdf_asset_id``), never copied.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ReferenceMeta(BaseModel):
    """The bibliographic fields a Literature document stores.

    Frozen, and an unknown key is refused. A write folds in only the fields
    the caller set (``exclude_unset``), so the ``source`` default is what an
    absent ``source`` reads as, never a value stamped over a stored one.

    Attributes:
        title: Work title.
        authors: Ordered author names.
        year: Publication year.
        doi: Digital Object Identifier.
        venue: Journal / conference / publisher.
        url: Canonical URL.
        pdf_path: Filesystem pointer to a PDF (never copied).
        pdf_asset_id: Asset id of an imported PDF, if any.
        source: Provenance label (``"manual"`` / ``"zotero"`` / …).
        source_key: Stable key in the external source (e.g. a Zotero key).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    doi: str | None = None
    venue: str | None = None
    url: str | None = None
    pdf_path: str | None = None
    pdf_asset_id: str | None = None
    source: str = "manual"
    source_key: str | None = None


__all__ = ["ReferenceMeta"]
