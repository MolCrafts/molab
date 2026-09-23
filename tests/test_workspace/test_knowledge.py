"""Knowledge Folder family — class via reflection, no type/kind/meta.json."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import Knowledge as KnowledgeConcept
from molab.workspace import (
    PLAN_BOOK_NAME,
    Finding,
    KnowledgeNotFoundError,
    Observation,
    Plan,
    Workspace,
)
from molab.workspace.folder import META_JSON_FILENAME, concept_from_dir, entity_filename
from molab.workspace.knowledge import parse_knowledge_class
from molab.workspace.validate import validate_workspace


def _ws(tmp_path: Path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="Lab")
    ws.materialize()
    return ws


class TestKnowledgeLayout:
    def test_project_and_experiment_knowledges_container(self, tmp_path: Path) -> None:
        project = _ws(tmp_path).add_project("peo-tg")
        exp = project.add_experiment("size-convergence")
        book = exp.add_knowledge(PLAN_BOOK_NAME, of=Plan, text="# Book\n")
        finding = project.add_knowledge("obs", of=Observation, text="hi\n")

        assert book.resolve() == Path(exp.resolve()) / "knowledges" / PLAN_BOOK_NAME
        assert (book.resolve() / "plan.json").is_file()
        assert not (book.resolve() / META_JSON_FILENAME).exists()
        import json

        payload = json.loads((book.resolve() / "plan.json").read_text())
        payload.pop("schema_version", None)
        assert "type" not in payload
        assert "kind" not in payload
        assert finding.resolve() == Path(project.resolve()) / "knowledges" / "obs"
        assert (finding.resolve() / "observation.json").is_file()
        assert not (Path(exp.resolve()) / "plan.md").exists()
        assert not (Path(exp.resolve()) / "plans").exists()

    def test_knowledge_getter_requires_existing(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        with pytest.raises(KnowledgeNotFoundError):
            exp.knowledge("missing")

    def test_add_is_idempotent_on_name(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        first = exp.add_knowledge("plan-book", of=Plan, text="kept\n")
        second = exp.add_knowledge("plan-book", of=Plan, text="new\n")
        assert first.resolve() == second.resolve()
        assert exp.knowledge("plan-book").read().startswith("new\n")

    def test_class_is_the_category(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        item = exp.add_knowledge("f1", of=Finding, text="n\n")
        assert isinstance(item, Finding)
        assert type(exp.knowledge("f1")) is Finding
        assert parse_knowledge_class("Plan") is Plan
        from molab.knowledge import Report as KnowledgeReport
        from molab.workspace.knowledge import Report as WorkspaceReport

        assert WorkspaceReport is KnowledgeReport
        with pytest.raises(ValueError, match="unknown knowledge class"):
            parse_knowledge_class("FailureAnalysis")


class TestKnowledgeRegistry:
    def test_entity_filename_from_class(self) -> None:
        assert entity_filename(Plan) == "plan.json"
        assert entity_filename(Finding) == "finding.json"

    def test_concept_from_dir_skips_knowledge_dirs(self, tmp_path: Path) -> None:
        project = _ws(tmp_path).add_project("p")
        book = project.add_knowledge("plan-book", of=Plan, text="# Hi\n")
        with pytest.raises(TypeError, match="Knowledge directory"):
            concept_from_dir(book.resolve(), project)
        rebuilt = KnowledgeConcept.open(book.resolve())
        assert isinstance(rebuilt, Plan)
        assert rebuilt.read() == "# Hi\n"

    def test_bundle_walk_finds_both_hosts(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        exp = project.add_experiment("e")
        project.add_knowledge("overview", of=Plan, text="p\n")
        exp.add_knowledge("plan-book", of=Plan, text="e\n")
        found = [c for c in KnowledgeConcept(ws.root).walk() if type(c).__name__ == "Plan"]
        assert {c.name for c in found} == {"overview", "plan-book"}
        assert {type(c).__name__ for c in found} == {"Plan"}
        assert type(project.knowledge("overview")) is Plan
        assert molab_knowledge_is_concept(project.knowledge("overview"))


def molab_knowledge_is_concept(item: object) -> bool:
    from molab.workspace.folder import Folder

    return not isinstance(item, Folder)


class TestKnowledgeValidate:
    def test_knowledges_container_is_not_stray(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("alpha")
        exp = project.add_experiment("sweep")
        project.add_knowledge("overview", of=Plan, text="p\n")
        exp.add_knowledge("plan-book", of=Plan, text="e\n")
        report = validate_workspace(ws.root)
        assert "layout.stray" not in {v.rule for v in report.errors}, report.violations

    def test_non_entity_under_knowledges_is_stray(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("alpha")
        (Path(project.resolve()) / "knowledges" / "scratch").mkdir(parents=True)
        report = validate_workspace(ws.root)
        stray = [v for v in report.errors if v.rule == "layout.stray"]
        assert any(v.path.endswith("knowledges/scratch") for v in stray)
