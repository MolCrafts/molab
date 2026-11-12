"""Read-only Zotero ingestion for the OKF workspace concepts (wsokf-05).

Reads a local ``zotero.sqlite`` (opened read-only) and yields one
:class:`~molab.knowledge.reference_meta.ReferenceMeta` per item: the fields a
:class:`~molab.knowledge.concepts.Literature` document stores, with ``source``
``"zotero"`` and the item key as ``source_key``. Each item's first PDF is
*resolved to a path* under Zotero's own ``storage/`` tree — no bytes are read
or copied. :meth:`Concept.import_zotero` writes them as Literature documents.
"""

from __future__ import annotations

import re
import sqlite3
from os import PathLike
from pathlib import Path

from .reference_meta import ReferenceMeta

_STORAGE_PREFIX = "storage:"
_YEAR = re.compile(r"\d{4}")


class ZoteroLibrary:
    """A local ``zotero.sqlite``, opened read-only."""

    def __init__(self, path: str | PathLike[str]) -> None:
        """Bind the database file. Nothing is read until :meth:`items`."""
        self.path = Path(path)

    def items(self) -> list[ReferenceMeta]:
        """Non-attachment, non-note items, as the fields a Literature stores.

        Only what the library holds is set, so a re-import leaves a field
        Zotero does not carry alone. Each regular item's PDF (if any) is
        resolved to ``<db_dir>/storage/<attachment_key>/<filename>`` without
        touching the file.
        """
        db = self.path
        storage_root = db.parent / "storage"
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT i.itemID, i.key FROM items i "
                "JOIN itemTypes it ON i.itemTypeID = it.itemTypeID "
                "WHERE it.typeName NOT IN ('attachment', 'note') "
                "ORDER BY i.itemID"
            ).fetchall()
            items: list[ReferenceMeta] = []
            for item_id, key in rows:
                fields = _item_fields(conn, item_id)
                found: dict[str, object] = {
                    "title": fields.get("title"),
                    "authors": _item_authors(conn, item_id) or None,
                    "year": _parse_year(fields.get("date")),
                    "doi": fields.get("DOI"),
                    "url": fields.get("url"),
                    "pdf_path": _item_pdf(conn, item_id, storage_root),
                    "source": "zotero",
                    "source_key": key,
                }
                items.append(
                    ReferenceMeta.model_validate(
                        {name: value for name, value in found.items() if value is not None}
                    )
                )
            return items
        finally:
            conn.close()


def _parse_year(date_value: str | None) -> int | None:
    if not date_value:
        return None
    match = _YEAR.search(date_value)
    return int(match.group()) if match else None


def _item_fields(conn: sqlite3.Connection, item_id: int) -> dict[str, str]:
    rows = conn.execute(
        "SELECT f.fieldName, idv.value FROM itemData d "
        "JOIN fields f ON d.fieldID = f.fieldID "
        "JOIN itemDataValues idv ON d.valueID = idv.valueID "
        "WHERE d.itemID = ?",
        (item_id,),
    ).fetchall()
    return dict(rows)


def _item_authors(conn: sqlite3.Connection, item_id: int) -> tuple[str, ...]:
    rows = conn.execute(
        "SELECT c.firstName, c.lastName FROM itemCreators ic "
        "JOIN creators c ON ic.creatorID = c.creatorID "
        "WHERE ic.itemID = ? ORDER BY ic.orderIndex",
        (item_id,),
    ).fetchall()
    names = [" ".join(p for p in (first, last) if p) for first, last in rows]
    return tuple(n for n in names if n)


def _item_pdf(conn: sqlite3.Connection, item_id: int, storage_root: Path) -> str | None:
    row = conn.execute(
        "SELECT a.path, i.key FROM itemAttachments a "
        "JOIN items i ON a.itemID = i.itemID "
        "WHERE a.parentItemID = ? AND a.path LIKE 'storage:%' "
        "AND a.contentType = 'application/pdf' LIMIT 1",
        (item_id,),
    ).fetchone()
    if row is None:
        return None
    path, attachment_key = row
    filename = path[len(_STORAGE_PREFIX) :]
    return str(storage_root / attachment_key / filename)


__all__ = ["ZoteroLibrary"]
