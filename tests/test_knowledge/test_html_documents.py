"""An HTML knowledge document (``knowledges/<slug>.html``) is first-class.

It is written, listed, read, searched, backlinked, renamed, moved, exported
and deleted through the same verbs as a markdown document; only its file
shape differs (the record in ``<script id="molab-record">``, the body
verbatim).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from molab import htmldoc
from molab.knowledge import Knowledge, Note, Roadmap, SourceRef
from molab.knowledge.concepts import _open_document
from molab.knowledge.record import record_of, replace_record
from molab.knowledge.write import write_knowledge

BODY = (
    "<molab-markdown>\n# Glass transition\n\nCooling rate matters.\n</molab-markdown>\n"
    '<molab-chart series="densityseries"></molab-chart>\n'
)
_ISO_SECONDS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")


def _html(lab: Any, name: str = "Tg page", body: str = BODY) -> Note:
    doc = write_knowledge(lab, name=name, of=Note, created_by="t", text=body, format="html")
    assert isinstance(doc, Note)
    return doc


class TestWrite:
    def test_lands_an_html_file_with_the_record_in_its_head(self, lab: Any) -> None:
        doc = _html(lab)

        assert Path(doc.path).name == "tg-page.html"
        text = Path(doc.path).read_text(encoding="utf-8")
        assert text.startswith("<!doctype html>\n")
        assert "<title>Tg page</title>" in text
        meta, body = htmldoc.split(text)
        assert body == BODY
        assert meta["class"] == "Note"
        assert meta["name"] == "Tg page"
        assert meta["created_by"] == "t"

    def test_create_stamps_created_at_once(self, lab: Any) -> None:
        doc = _html(lab)
        stamp = doc.frontmatter()["created_at"]
        assert isinstance(stamp, str)
        assert _ISO_SECONDS.match(stamp)

        write_knowledge(lab, name="Tg page", of=Note, created_by="u", text="<p>new</p>")
        assert doc.frontmatter()["created_at"] == stamp
        assert doc.read() == "<p>new</p>"

    def test_markdown_create_stamps_created_at_too(self, lab: Any) -> None:
        doc = write_knowledge(lab, name="md", of=Note, created_by="t", text="x")
        assert _ISO_SECONDS.match(str(doc.frontmatter()["created_at"]))

    def test_an_existing_document_keeps_its_format(self, lab: Any) -> None:
        doc = _html(lab)
        again = write_knowledge(lab, name="Tg page", of=Note, created_by="t", text="")
        assert again.path == doc.path
        assert again.read() == BODY

    def test_create_refuses_a_name_in_the_other_format(self, lab: Any) -> None:
        _html(lab)
        with pytest.raises(ValueError, match="already exists"):
            write_knowledge(lab, name="Tg page", of=Note, created_by="t", text="x", format="md")
        write_knowledge(lab, name="plain", of=Note, created_by="t", text="x")
        with pytest.raises(ValueError, match="already exists"):
            write_knowledge(lab, name="plain", of=Note, created_by="t", text="x", format="html")

    def test_a_cite_lands_in_its_own_markdown_block(self, lab: Any) -> None:
        target = write_knowledge(lab, name="other", of=Note, created_by="t", text="# Other")
        doc = _html(lab)
        doc.ref(target)

        body = doc.read()
        assert body.startswith(BODY)
        assert body[len(BODY) :] == "<molab-markdown>\n- [other.md](other.md)\n</molab-markdown>\n"
        assert [edge.target for edge in doc.links()] == [str(target.path)]

    def test_a_sourced_html_document_keeps_its_sources(self, experiment: Any) -> None:
        doc = write_knowledge(
            experiment,
            name="finding",
            of=Roadmap,
            sources=[SourceRef.of(experiment)],
            created_by="t",
            text="<p>plan</p>\n",
            record={"stages": [{"id": "s1", "title": "One"}]},
            format="html",
        )
        assert Path(doc.path).suffix == ".html"
        assert "<molab-markdown>\n" in doc.read()
        assert len(doc.sources) == 1  # ty: ignore[unresolved-attribute]

    def test_replace_record_keeps_the_html_form(self, experiment: Any) -> None:
        doc = write_knowledge(
            experiment,
            name="road",
            of=Roadmap,
            sources=[SourceRef.of(experiment)],
            created_by="t",
            text="<p>plan</p>\n",
            record={"stages": [{"id": "s1", "title": "One"}]},
            format="html",
        )
        replace_record(doc, {"stages": [{"id": "s2", "title": "Two"}]})

        assert Path(doc.path).read_text(encoding="utf-8").startswith("<!doctype html>")
        assert record_of(doc)["stages"] == [{"id": "s2", "title": "Two"}]
        assert "created_at" not in record_of(doc)
        assert doc.read().startswith("<p>plan</p>\n")


class TestRead:
    def test_walk_and_open_find_it(self, lab: Any) -> None:
        doc = _html(lab)

        assert [item.path for item in Knowledge(lab.root, fs=lab.fs).walk()] == [doc.path]
        suffixless = str(doc.path)[: -len(".html")]
        assert _open_document(suffixless).path == doc.path
        opened = _open_document(doc.path)
        assert isinstance(opened, Note)
        assert opened.name == "tg-page"
        assert opened.read() == BODY

    def test_search_ranks_text_not_tags(self, lab: Any) -> None:
        _html(lab)
        root = Knowledge(lab.root, fs=lab.fs)

        hits = root.search("cooling").hits
        assert [hit.entry.path for hit in hits] == ["knowledges/tg-page.html"]
        assert hits[0].entry.title == "Tg page"
        assert not root.search("molab").hits
        assert not root.search("densityseries").hits

    def test_export_is_the_whole_html_file(self, lab: Any) -> None:
        doc = _html(lab)
        assert doc.export() == Path(doc.path).read_text(encoding="utf-8")


class TestGraph:
    def test_backlinks_rename_move_and_delete(self, lab: Any, experiment: Any) -> None:
        target = write_knowledge(lab, name="target", of=Note, created_by="t", text="# T")
        doc = _html(lab)
        doc.ref(target)
        citing = write_knowledge(lab, name="citer", of=Note, created_by="t", text="# C")
        citing.ref(doc)

        assert [link.source.path for link in doc.backlinks(within=lab.root)] == [citing.path]
        assert [link.source.path for link in target.backlinks(within=lab.root)] == [doc.path]

        doc.rename("Renamed page", within=lab.root)
        assert Path(doc.path).name == "renamed-page.html"
        assert "(renamed-page.html)" in citing.read()

        doc.move_to(experiment, within=lab.root)
        assert Path(doc.path).parent == Path(str(experiment.resolve())) / "knowledges"
        assert Path(doc.path).suffix == ".html"
        assert "experiments/e/knowledges/renamed-page.html" in citing.read()
        assert "../../../../knowledges/target.md" in doc.read()

        doc.move_to(lab, stem="kept", within=lab.root)
        assert Path(doc.path).name == "kept.html"

        doc.delete()
        assert not Path(doc.path).exists()
