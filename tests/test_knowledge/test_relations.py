from __future__ import annotations

import pytest

from molab.knowledge.concepts import Note
from molab.knowledge.record import RecordConflictError, digest_of
from molab.knowledge.relations import mutate_relation, relation_links


def test_edit_preserves_narrative_record_examples_images_and_target_spelling(tmp_path):
    doc = Note(tmp_path / "knowledges" / "idea")
    body = (
        "# Idea\n\nSee [@supports Result](./result.md#evidence) for details.\n"
        "`[example](code.md)`\n\n```md\n[example](fenced.md)\n```\n"
        "![figure](figure.png)\n[anchor](#part)\n"
        "- [@cites Paper](https://example.org/paper)\n"
    )
    doc.write(body, tags=["keep"])
    links = relation_links(doc)
    assert len(links) == 2
    assert links[0].target == f"{tmp_path}/knowledges/result.md#evidence"
    mutate_relation(
        doc, action="replace", occurrence=0, role="contradicts", if_match=digest_of(doc)
    )
    assert doc.read() == body.replace("@supports Result", "@contradicts Result")
    assert doc.tags() == ["keep"]
    mutate_relation(doc, action="remove", occurrence=0, if_match=digest_of(doc))
    assert "See Result for details." in doc.read()
    mutate_relation(doc, action="remove", occurrence=0, if_match=digest_of(doc))
    assert "Paper" not in doc.read()
    assert "![figure](figure.png)" in doc.read()
    assert "[example](fenced.md)" in doc.read()


def test_occurrence_and_digest_prevent_wrong_or_stale_edits(tmp_path):
    doc = Note(tmp_path / "knowledges" / "idea")
    doc.write("[First](result.md) and [Second](result.md).\n")
    digest = digest_of(doc)
    mutate_relation(doc, action="replace", occurrence=1, role="supports", if_match=digest)
    assert doc.read() == "[First](result.md) and [@supports Second](result.md).\n"
    with pytest.raises(RecordConflictError):
        mutate_relation(doc, action="remove", occurrence=0, if_match=digest)
    with pytest.raises(ValueError, match="occurrence"):
        mutate_relation(doc, action="remove", occurrence=5, if_match=digest_of(doc))
    with pytest.raises(ValueError, match="sigil"):
        mutate_relation(
            doc,
            action="add",
            target="molab:experiment/E1",
            text="@supports misleading",
            role="references",
            if_match=digest_of(doc),
        )


@pytest.mark.parametrize("suffix", ["md", "html"])
def test_add_uses_canonical_links_for_documents_refs_and_web(tmp_path, suffix):
    doc = Note(tmp_path / "knowledges" / f"idea.{suffix}")
    doc.write("# Idea\n")
    for target, role in [
        (str(tmp_path / "knowledges" / "result.md"), "supports"),
        ("molab:experiment/E1/run/R1", "records"),
        ("https://example.org/paper", "cites"),
    ]:
        mutate_relation(
            doc, action="add", target=target, role=role, text="Evidence", if_match=digest_of(doc)
        )
    assert [link.role for link in relation_links(doc)] == ["supports", "records", "cites"]
    assert [link.label for link in relation_links(doc)] == ["Evidence"] * 3
    mutate_relation(doc, action="remove", occurrence=1, if_match=digest_of(doc))
    assert [link.role for link in relation_links(doc)] == ["supports", "cites"]
    if suffix == "html":
        assert "<molab-markdown>" in doc.read()
