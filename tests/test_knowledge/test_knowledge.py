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
        finding = Finding(tmp_path / "result", sources=[SourceRef(kind="run", ref="run-1")])
        finding.write("# Result\n")
        text = finding.path.read_text()
        assert "class: Finding" in text
        assert "ref: run-1" in text

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


class TestKnowledgeWalk:
    """``walk`` yields markdown files under ``knowledges/``."""

    def test_walk_yields_only_knowledges_markdown(self, tmp_path: Path) -> None:
        root = tmp_path / "wiki"
        kb = root / "knowledges"
        kb.mkdir(parents=True)
        (kb / "cooling.md").write_text("---\nclass: Note\n---\n\n# Cooling rate\n")
        run_dir = root / "run"
        run_dir.mkdir()
        (run_dir / "run.json").write_text("{}\n")
        e1 = run_dir / "executions" / "e1"
        e1.mkdir(parents=True)
        (e1 / "index.md").write_text("# decoy\n")

        yielded = {item.name for item in Knowledge(root).walk()}
        assert yielded == {"cooling"}
        assert "run" not in yielded
        assert "e1" not in yielded

    def test_walk_follows_layout_containers_not_bulk_trees(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        (root / "knowledges").mkdir(parents=True)
        (root / "knowledges" / "lab-note.md").write_text("---\nclass: Note\n---\n\n# Lab\n")
        exp_k = root / "projects" / "p" / "experiments" / "e" / "knowledges"
        exp_k.mkdir(parents=True)
        (exp_k / "finding.md").write_text("---\nclass: Note\n---\n\n# F\n")
        run_k = root / "projects" / "p" / "experiments" / "e" / "runs" / "r" / "knowledges"
        run_k.mkdir(parents=True)
        (run_k / "log.md").write_text("---\nclass: Note\n---\n\n# Log\n")
        decoy = root / "projects" / "p" / "experiments" / "e" / "pinn-src" / "knowledges"
        decoy.mkdir(parents=True)
        (decoy / "noise.md").write_text("---\nclass: Note\n---\n\n# Noise\n")
        campaign = root / "projects" / "p" / "campaign" / "knowledges"
        campaign.mkdir(parents=True)
        (campaign / "old.md").write_text("---\nclass: Note\n---\n\n# Old\n")

        yielded = {item.name for item in Knowledge(root).walk()}
        assert yielded == {"lab-note", "finding", "log"}
        assert "noise" not in yielded
        assert "old" not in yielded


class TestKnowledgeSearch:
    """``search(..., of=Note)`` ranks only Note hits."""

    def test_search_by_note_class_excludes_other_subclasses(self, tmp_path: Path) -> None:
        root = tmp_path / "wiki"
        kb = root / "knowledges"
        kb.mkdir(parents=True)
        (kb / "cooling.md").write_text(
            "---\nclass: Note\n---\n\n# Cooling rate\n\nQuench protocol.\n"
        )
        (kb / "paper.md").write_text(
            "---\nclass: Literature\ntitle: Cooling of glasses\nyear: 2015\n---\n\n"
            "cooling in the literature\n"
        )

        result = Knowledge(root).search("cooling", of=Note)
        assert {hit.entry.path for hit in result.hits} == {"knowledges/cooling.md"}


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
        finding = Finding(
            experiment, "tg-rise", sources=[SourceRef(kind="experiment", ref="exp-1")]
        )

        assert finding.path == Path(str(experiment.resolve())) / "knowledges" / "tg-rise.md"

    def test_sources_stay_required_in_the_host_form(self, experiment: Experiment) -> None:
        with pytest.raises(ValueError):
            Finding(experiment, "tg-rise")

    def test_the_narrative_write_lands_at_the_host_path(self, experiment: Experiment) -> None:
        source = SourceRef(kind="experiment", ref="exp-1")
        finding = Finding(experiment, "tg-rise", sources=[source])

        finding.write("# Tg rises with the cooling rate\n")

        assert finding.path.is_file()
        assert finding.path.read_text().endswith("# Tg rises with the cooling rate\n")
        assert finding.sources == [source]
