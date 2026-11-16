"""``molab knowledge bib``: a Manuscript's bibliography, written from the Literature it cites."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from molab.cli.knowledge_cmd import knowledge_app
from molab.knowledge import Literature, Manuscript, Note, SourceRef
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace

DOC = "knowledges/paper.tex"


@pytest.fixture
def lab(tmp_path: Path) -> Workspace:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    write_knowledge(
        workspace,
        name="evans1990",
        of=Literature,
        created_by="t",
        text="abstract",
        fields={
            "title": "Nonequilibrium Liquids",
            "authors": ["D. J. Evans"],
            "year": 1990,
            "doi": "10.1/x",
        },
    )
    outline = write_knowledge(workspace, name="outline", of=Note, created_by="t", text="# Outline")
    write_knowledge(
        workspace,
        name="paper",
        of=Manuscript,
        created_by="author",
        text="\\documentclass{article}\\begin{document}\\cite{evans1990}\\end{document}\n",
        sources=[SourceRef.of(outline)],
    )
    return workspace


def _bib(lab: Workspace, *args: str) -> Any:
    return CliRunner().invoke(knowledge_app, ["bib", DOC, *args, "--path", str(lab.root)])


def test_prints_one_entry_per_cited_literature(lab: Workspace) -> None:
    result = _bib(lab)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("@misc{evans1990,\n")
    assert "  doi = {10.1/x},\n" in result.stdout


def test_writes_the_bibliography_to_a_file(lab: Workspace, tmp_path: Path) -> None:
    out = tmp_path / "build" / "references.bib"
    result = _bib(lab, "--out", str(out))
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8").startswith("@misc{evans1990,\n")


def test_refuses_a_key_no_literature_answers(lab: Workspace) -> None:
    paper = Path(str(lab.root)) / DOC
    paper.write_text(
        paper.read_text(encoding="utf-8").replace("evans1990", "nobody"), encoding="utf-8"
    )
    result = _bib(lab)
    assert result.exit_code == 1
    assert "nobody" in result.output


def test_refuses_a_document_that_is_not_a_manuscript(lab: Workspace) -> None:
    result = CliRunner().invoke(
        knowledge_app, ["bib", "knowledges/outline.md", "--path", str(lab.root)]
    )
    assert result.exit_code == 1
    assert "not a Manuscript" in result.output
