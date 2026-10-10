"""``Knowledge`` handle: ``write``, ``from_dir``, ``walk``, ``search``."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import (
    Finding,
    Knowledge,
    KnowledgeNotFoundError,
    Literature,
    Note,
    ReferenceMeta,
    SourceRef,
)
from molab.workspace import Experiment, Workspace


@pytest.fixture
def experiment(tmp_path: Path) -> Experiment:
    """A real workspace Experiment — the Folder-family host."""
    workspace = Workspace(root=tmp_path / "lab")
    workspace.materialize()
    return workspace.add_project("p").add_experiment("e")


class TestWrite:
    """Public write is one markdown file with ``class:`` frontmatter."""

    def test_note_construction_creates_no_files(self, tmp_path: Path) -> None:
        note = Note(tmp_path / "idea")
        assert note.path.name == "idea.md"
        assert not note.path.exists()

    def test_note_write_creates_markdown_not_json(self, tmp_path: Path) -> None:
        note = Note(tmp_path / "idea")
        note.write("# Hello\n")
        assert note.path.is_file()
        text = note.path.read_text()
        assert "class: Note" in text
        assert "# Hello" in text
        assert not (tmp_path / "idea" / "note.json").exists()
        assert not (tmp_path / "meta.json").exists()

    def test_literature_write_persists_bib_in_frontmatter(self, tmp_path: Path) -> None:
        lit = Literature(tmp_path / "lecun2015")
        lit.write(ReferenceMeta(title="Deep Learning", year=2015))
        assert "title: Deep Learning" in lit.path.read_text()
        assert lit.record.title == "Deep Learning"
        assert lit.record.year == 2015

    def test_finding_write_persists_source_ref(self, tmp_path: Path) -> None:
        finding = Finding(
            tmp_path / "result",
            sources=[SourceRef(kind="run", ref="molab:experiment/E1/run/R1")],
        )
        finding.write("# Result\n")
        text = finding.path.read_text()
        assert "class: Finding" in text
        assert "sources:" not in text
        assert "- [@derived_from R1](molab:experiment/E1/run/R1)" in text

    def test_finding_without_sources_raises_at_construct(self, tmp_path: Path) -> None:
        with pytest.raises((TypeError, ValueError)):
            Finding(tmp_path / "unsourced")


class TestFromDir:
    """``Knowledge.open`` rebuilds the subclass from frontmatter ``class``."""

    def test_from_dir_returns_note(self, tmp_path: Path) -> None:
        path = tmp_path / "idea.md"
        path.write_text("---\nclass: Note\n---\n\n# Hi\n")
        rebuilt = Knowledge.open(path)
        assert isinstance(rebuilt, Note)
        assert rebuilt.read().startswith("# Hi")

    def test_from_dir_returns_literature(self, tmp_path: Path) -> None:
        path = tmp_path / "lecun2015.md"
        path.write_text("---\nclass: Literature\ntitle: Deep Learning\nyear: 2015\n---\n")
        rebuilt = Knowledge.open(path)
        assert isinstance(rebuilt, Literature)

    def test_missing_six_class_files_raises(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(KnowledgeNotFoundError):
            Knowledge.open(tmp_path / "empty")


class TestCite:
    """All six classes cite with the same verb."""

    def test_finding_cites_literature(self, tmp_path: Path) -> None:
        lit = Literature(tmp_path / "paper")
        lit.write("FeNNol.\n")
        finding = Finding(
            tmp_path / "tf32",
            sources=[SourceRef(kind="file", ref="paper/index.md")],
        )
        finding.write("# TF32\n")
        finding.cite(lit)
        assert any(Path(edge.target) == lit.path for edge in finding.links())


class TestSourcedHostConstruction:
    """A sourced class takes ``(host, name)`` too; ``sources`` stays required."""

    def test_a_finding_lands_on_the_host_markdown_golden(self, experiment: Experiment) -> None:
        finding = Finding(experiment, "tg-rise", sources=[SourceRef.of(experiment)])

        assert finding.path == Path(str(experiment.resolve())) / "knowledges" / "tg-rise.md"

    def test_sources_stay_required_in_the_host_form(self, experiment: Experiment) -> None:
        with pytest.raises(ValueError):
            Finding(experiment, "tg-rise")

    def test_the_narrative_write_lands_at_the_host_path(self, experiment: Experiment) -> None:
        source = SourceRef.of(experiment)
        finding = Finding(experiment, "tg-rise", sources=[source])

        finding.write("# Tg rises with the cooling rate\n")

        assert finding.path.is_file()
        text = finding.path.read_text()
        assert "# Tg rises with the cooling rate\n" in text
        assert "sources:" not in text
        assert finding.sources == [source]
