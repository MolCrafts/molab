"""Tests for read-only Zotero import → ``Literature`` records.

Covers ``molab.knowledge.zotero`` (``ZoteroItem`` / ``read_zotero``)
and its concept-producing consumer ``Concept.import_zotero``. A minimal
``zotero.sqlite`` is built in-place (the real schema subset the reader touches),
then imported through a knowledge root handle. PDFs are
*pointed at* via ``pdf_path`` — no bytes are copied into the bundle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from molab.knowledge.concept import Concept
from molab.knowledge.zotero import ZoteroItem, read_zotero


def _make_zotero_db(data_dir: Path) -> Path:
    """Build a minimal zotero.sqlite + storage tree; return the db path."""
    db = data_dir / "zotero.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT, itemTypeID INTEGER);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT);
        CREATE TABLE itemCreators (itemID INTEGER, creatorID INTEGER, orderIndex INTEGER);
        CREATE TABLE itemAttachments (
            itemID INTEGER, parentItemID INTEGER, path TEXT, contentType TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO itemTypes VALUES (?, ?)",
        [(1, "journalArticle"), (2, "attachment")],
    )
    conn.executemany(
        "INSERT INTO fields VALUES (?, ?)",
        [(1, "title"), (2, "DOI"), (3, "url"), (4, "date")],
    )
    conn.executemany(
        "INSERT INTO items VALUES (?, ?, ?)",
        [(10, "AAAA", 1), (11, "BBBB", 1), (20, "CCCC", 2)],
    )
    conn.executemany(
        "INSERT INTO itemDataValues VALUES (?, ?)",
        [
            (1, "Deep Learning"),
            (2, "10.1/x"),
            (3, "http://ex.com"),
            (4, "2015-05-01"),
            (5, "No PDF Paper"),
            (6, "2020"),
        ],
    )
    conn.executemany(
        "INSERT INTO itemData VALUES (?, ?, ?)",
        [
            (10, 1, 1),  # title
            (10, 2, 2),  # DOI
            (10, 3, 3),  # url
            (10, 4, 4),  # date
            (11, 1, 5),  # title
            (11, 4, 6),  # date
        ],
    )
    conn.executemany(
        "INSERT INTO creators VALUES (?, ?, ?)",
        [(100, "Yann", "LeCun")],
    )
    conn.executemany("INSERT INTO itemCreators VALUES (?, ?, ?)", [(10, 100, 0)])
    conn.executemany(
        "INSERT INTO itemAttachments VALUES (?, ?, ?, ?)",
        [(20, 10, "storage:paper.pdf", "application/pdf")],
    )
    conn.commit()
    conn.close()
    return db


class TestReadZoteroItems:
    """``read_zotero`` — parse a ``zotero.sqlite`` into ``ZoteroItem`` records."""

    def test_parses_bib_fields_and_resolves_pdf_pointer(self, tmp_path: Path) -> None:
        db = _make_zotero_db(tmp_path)
        items = {i.key: i for i in read_zotero(db)}
        assert set(items) == {"AAAA", "BBBB"}  # attachment item excluded

        a = items["AAAA"]
        assert isinstance(a, ZoteroItem)
        assert a.title == "Deep Learning"
        assert a.authors == ("Yann LeCun",)
        assert a.year == 2015
        assert a.doi == "10.1/x"
        assert a.pdf_path is not None
        assert a.pdf_path.endswith("storage/CCCC/paper.pdf")

        assert items["BBBB"].year == 2020
        assert items["BBBB"].pdf_path is None  # no attachment

    def test_opens_database_read_only(self, tmp_path: Path) -> None:
        db = _make_zotero_db(tmp_path)
        before = db.read_bytes()
        read_zotero(db)
        assert db.read_bytes() == before  # opened read-only, never mutated


class TestConceptImportZotero:
    """``Concept.import_zotero`` — link a Zotero library as literature documents."""

    def test_import_writes_no_sources_json(self, tmp_path: Path) -> None:
        # arch-own-01-cleanup: the persisted ``sources.json`` link record is gone.
        src = tmp_path / "zotero"
        src.mkdir()
        db = _make_zotero_db(src)
        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        b = Concept(bundle_root)

        refs = b.import_zotero(db)

        assert len(refs) == 2
        assert not (bundle_root / "sources.json").exists()
