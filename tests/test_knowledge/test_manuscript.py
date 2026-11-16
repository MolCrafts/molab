"""A Manuscript is a knowledge document stored as LaTeX (``knowledges/<slug>.tex``).

Its record is a leading comment block, so the file compiles as it stands. Its
sources are whole-line comment links. Each ``\\cite`` key is the name of a
Literature document in its host or a host above it; that is its ``cites``
edge, and molab writes its bibliography from those documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab import texdoc
from molab.knowledge import Literature, Manuscript, Note, Plan, SourceRef
from molab.knowledge.concepts import _open_document
from molab.knowledge.validate import validate_knowledge
from molab.knowledge.write import write_knowledge

BODY = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "Shear thinning of molten NaCl~\\cite{petravic2003, evans1990}.\n"
    "The indicator $\\mathbf{1}_{[0,1](x)}$ is mathematics, not a link.\n"
    "\\bibliography{references}\n"
    "\\end{document}\n"
)


def _literature(host: Any, name: str, **fields: object) -> Literature:
    doc = write_knowledge(
        host, name=name, of=Literature, created_by="t", text="abstract", fields=fields
    )
    assert isinstance(doc, Literature)
    return doc


def _outline(host: Any) -> Plan:
    doc = write_knowledge(
        host,
        name="outline",
        of=Plan,
        created_by="t",
        text="# Outline",
        sources=[SourceRef.of(host)],
    )
    assert isinstance(doc, Plan)
    return doc


def _manuscript(host: Any, body: str = BODY) -> Manuscript:
    outline = _outline(host)
    doc = write_knowledge(
        host,
        name="NaCl NEMD",
        of=Manuscript,
        created_by="author",
        text=body,
        sources=[SourceRef.of(outline)],
    )
    assert isinstance(doc, Manuscript)
    return doc


@pytest.fixture
def project(lab: Any) -> Any:
    return lab.get_project("p")


@pytest.fixture
def cited(lab: Any, project: Any) -> tuple[Literature, Literature]:
    """One cited work in the project, one in the workspace root above it."""
    near = _literature(
        project,
        "petravic2003",
        title="Shear viscosity of molten NaCl & KCl at 100% strain",
        authors=["J. Petravic", "J. Delhommelle"],
        year=2003,
        venue="J. Chem. Phys.",
        doi="10.1063/1.1562610",
    )
    far = _literature(
        lab,
        "evans1990",
        title="Statistical Mechanics of Nonequilibrium Liquids",
        authors=["D. J. Evans"],
        year=1990,
        url="https://example.org/evans",
    )
    return near, far


class TestStorage:
    def test_lands_a_tex_file_that_compiles_as_it_stands(self, project: Any) -> None:
        doc = _manuscript(project)

        assert Path(doc.path).name == "nacl-nemd.tex"
        text = Path(doc.path).read_text(encoding="utf-8")
        head = text[: text.index("\\documentclass")]
        assert all(line.startswith("%") for line in head.splitlines())
        meta, body = texdoc.split(text)
        assert meta["class"] == "Manuscript"
        assert meta["name"] == "NaCl NEMD"
        assert body.startswith(BODY)

    def test_reopens_as_a_manuscript_with_its_body(self, project: Any) -> None:
        doc = _manuscript(project)
        again = _open_document(doc.path)
        assert isinstance(again, Manuscript)
        assert again.read().startswith(BODY)

    def test_sources_are_comment_links_and_latex_is_not_a_link(self, project: Any) -> None:
        doc = _manuscript(project)

        body = doc.read()
        assert "% - [@derived_from" in body
        targets = [edge.target for edge in doc.links() if edge.role == "derived_from"]
        assert targets == [str(Path(project.resolve()) / "knowledges" / "outline.md")]
        assert [edge.role for edge in doc.links()] == ["derived_from"]

    def test_a_manuscript_is_only_tex_and_tex_is_only_a_manuscript(self, project: Any) -> None:
        outline = _outline(project)
        with pytest.raises(ValueError, match="tex"):
            write_knowledge(
                project,
                name="m",
                of=Manuscript,
                created_by="t",
                text="x",
                sources=[SourceRef.of(outline)],
                format="md",
            )
        with pytest.raises(ValueError, match="tex"):
            write_knowledge(project, name="n", of=Note, created_by="t", text="x", format="tex")

    def test_validate_refuses_a_tex_file_of_another_class(self, lab: Any, project: Any) -> None:
        container = Path(project.resolve()) / "knowledges"
        container.mkdir(exist_ok=True)
        (container / "loose.tex").write_text(texdoc.dump({"class": "Note", "name": "loose"}, "x\n"))

        rules = [(issue["rule"], issue["path"]) for issue in validate_knowledge(lab)]
        assert ("knowledge.class", "projects/p/knowledges/loose.tex") in rules


class TestCitations:
    def test_each_cite_key_is_a_literature_in_this_host_or_above(
        self, project: Any, cited: Any
    ) -> None:
        near, far = cited
        doc = _manuscript(project)

        assert doc.citations() == [("petravic2003", near), ("evans1990", far)]
        cites = [edge.target for edge in doc.links() if edge.role == "cites"]
        assert cites == [str(near.path), str(far.path)]
        assert [link.source for link in near.backlinks()] == [doc]

    def test_a_key_no_literature_answers_is_a_validate_error(
        self, lab: Any, project: Any, cited: Any
    ) -> None:
        _manuscript(project, BODY.replace("evans1990", "nobody2020"))

        found = [i for i in validate_knowledge(lab) if i["rule"] == "knowledge.citation"]
        assert [(i["path"], i["severity"]) for i in found] == [
            ("projects/p/knowledges/nacl-nemd.tex", "error")
        ]
        assert "nobody2020" in found[0]["detail"]

    def test_a_note_named_like_the_key_is_not_a_citation(self, project: Any, cited: Any) -> None:
        write_knowledge(project, name="nobody2020", of=Note, created_by="t", text="x")
        doc = _manuscript(project, BODY.replace("evans1990", "nobody2020"))
        assert doc.citations()[1] == ("nobody2020", None)

    def test_bibliography_is_one_entry_per_cited_literature(self, project: Any, cited: Any) -> None:
        doc = _manuscript(project)

        bib = doc.bibliography()
        first, second = bib.split("\n\n")
        assert first.startswith("@article{petravic2003,\n")
        assert "  author = {J. Petravic and J. Delhommelle},\n" in first
        assert "  title = {{Shear viscosity of molten NaCl \\& KCl at 100\\% strain}},\n" in first
        assert "  journal = {J. Chem. Phys.},\n" in first
        assert "  year = {2003},\n" in first
        assert "  doi = {10.1063/1.1562610},\n" in first
        assert second.startswith("@misc{evans1990,\n")
        assert "  url = {https://example.org/evans},\n" in second

    def test_bibliography_refuses_a_key_no_literature_answers(
        self, project: Any, cited: Any
    ) -> None:
        doc = _manuscript(project, BODY.replace("evans1990", "nobody2020"))
        with pytest.raises(ValueError, match="nobody2020"):
            doc.bibliography()


class TestFollowingTheCitedLiterature:
    def test_renaming_a_cited_literature_rewrites_the_cite_key(
        self, lab: Any, project: Any, cited: Any
    ) -> None:
        near, _far = cited
        doc = _manuscript(project)

        near.rename("petravic2003shear")

        assert "\\cite{petravic2003shear, evans1990}" in doc.read()
        assert doc.citations()[0] == ("petravic2003shear", near)
        assert [i for i in validate_knowledge(lab) if i["rule"] == "knowledge.citation"] == []

    def test_the_key_follows_the_renamed_work_past_a_namesake_above(
        self, lab: Any, project: Any, cited: Any
    ) -> None:
        near, _far = cited
        _literature(lab, "petravic2003", title="Namesake", authors=["X"], year=2003, doi="10.1/n")
        doc = _manuscript(project)

        near.rename("petravic2003shear")

        assert doc.citations()[0] == ("petravic2003shear", near)

    def test_superseding_a_cited_literature_rewrites_the_cite_key(
        self, lab: Any, project: Any, cited: Any
    ) -> None:
        near, _far = cited
        doc = _manuscript(project)

        successor = write_knowledge(
            project,
            name="petravic2003b",
            of=Literature,
            created_by="t",
            text="abstract",
            fields={"title": "Erratum", "authors": ["J. Petravic"], "year": 2003, "doi": "10.1/e"},
            replaces=[str(near.path)],
        )

        assert "\\cite{petravic2003b, evans1990}" in doc.read()
        assert doc.citations()[0] == ("petravic2003b", successor)

    def test_moving_a_cited_literature_up_keeps_the_key(
        self, lab: Any, project: Any, cited: Any
    ) -> None:
        near, _far = cited
        doc = _manuscript(project)

        near.move_to(lab)

        assert "\\cite{petravic2003, evans1990}" in doc.read()
        assert doc.citations()[0] == ("petravic2003", near)
