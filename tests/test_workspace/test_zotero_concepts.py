"""Tests for read-only Zotero import → ``Literature`` records.

Covers ``molab.knowledge.zotero`` (``ZoteroLibrary.items``)
and its concept-producing consumer ``Concept.import_zotero``. A minimal
``zotero.sqlite`` is built in-place (the real schema subset the reader touches),
then imported through a knowledge root handle. PDFs are
*pointed at* via ``pdf_path`` — no bytes are copied into the bundle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from molab.knowledge.concept import Concept
from molab.knowledge.concepts import LiteratureFields
from molab.knowledge.zotero import ZoteroLibrary


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
    """``ZoteroLibrary.items`` — parse a ``zotero.sqlite`` into records."""

    def test_parses_bib_fields_and_resolves_pdf_pointer(self, tmp_path: Path) -> None:
        db = _make_zotero_db(tmp_path)
        items = {i.source_key: i for i in ZoteroLibrary(db).items()}
        assert set(items) == {"AAAA", "BBBB"}  # attachment item excluded

        a = items["AAAA"]
        assert isinstance(a, LiteratureFields)
        assert a.source == "zotero"
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
        ZoteroLibrary(db).items()
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

    def test_a_reimport_keeps_tags_and_source(self, tmp_path: Path) -> None:
        # The bib record carried a ``tags=[]`` default and a ``source="manual"``
        # default, so every rewrite cleared the stored tags and relabelled a
        # Zotero record as manual.
        from molab.knowledge.concepts import Literature
        from molab.knowledge.write import write_knowledge

        src = tmp_path / "zotero"
        src.mkdir()
        db = _make_zotero_db(src)
        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        root = Concept(bundle_root)
        first = {ref.name: ref for ref in root.import_zotero(db)}["aaaa"]
        first.write(tags=["glass", "ml"])

        again = {ref.name: ref for ref in root.import_zotero(db)}["aaaa"]
        assert again.tags() == ["glass", "ml"]
        assert again.frontmatter()["source"] == "zotero"

        write_knowledge(root, name="AAAA", of=Literature, created_by="t", text="", **_bib_title())
        reread = Literature(first.path)
        assert reread.tags() == ["glass", "ml"]
        assert reread.frontmatter()["source"] == "zotero"
        assert reread.frontmatter()["title"] == "Renamed"


def _bib_title() -> dict[str, object]:
    """A rewrite that sets only the title."""
    return {"fields": {"title": "Renamed"}}
