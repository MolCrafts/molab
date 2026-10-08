"""Unit tests for :mod:`molab.services.knowledge_context` (knowledge-crossref-04).

The projection's goldens are the **file form** (D17): a Note lands as
``knowledges/<name>.md``, never a directory holding ``note.json``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import Note
from molab.services.knowledge_context import (
    KnowledgeContext,
    KnowledgeRef,
    context_with_knowledge,
    project_knowledge,
)
from molab.workspace import ContextFocus, Workspace, WorkspaceRef
from molab.workspace.run import Run
from molab.workspace.workspace_context import WorkspaceContext, assemble_workspace_context


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    return ws


def _files(root: Path) -> set[str]:
    """Every path under *root* except the git store — the write detector."""
    return {
        str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.relative_to(root).parts
    }


def _tree(ws: Workspace) -> set[str]:
    """The write detector over a workspace root (``Workspace.root`` is ``molab.Path``)."""
    return _files(Path(str(ws.root)))


class TestProjectKnowledge:
    def test_projects_the_file_form_row(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note.mount(ws, "Idea", body="# Idea\n")
        assert project_knowledge(ws) == [
            KnowledgeRef(path="knowledges/idea.md", type="Note", title="Idea", id="idea")
        ]

    def test_empty_workspace_projects_nothing(self, tmp_path: Path) -> None:
        assert project_knowledge(_workspace(tmp_path)) == []

    def test_title_falls_back_to_the_document_name(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note.mount(ws, "No Heading", body="plain prose, no H1\n")
        assert project_knowledge(ws) == [
            KnowledgeRef(
                path="knowledges/no-heading.md",
                type="Note",
                title="no-heading",
                id="no-heading",
            )
        ]

    def test_projection_writes_nothing(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note.mount(ws, "Idea", body="# Idea\n")
        before = _tree(ws)
        project_knowledge(ws)
        assert _tree(ws) == before

    def test_bulk_trees_are_not_projected(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note.mount(ws, "Idea", body="# Idea\n")
        # ``executions/`` is pruned by the Knowledge walk — a document-looking
        # file beneath it is run output, not knowledge.
        Note(ws.root / "executions" / "e01" / "knowledges" / "hidden").write("# Hidden\n")
        assert [row.path for row in project_knowledge(ws)] == ["knowledges/idea.md"]


class TestContextWithKnowledge:
    def test_returns_complete_context_with_projected_knowledge(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        run: Run = experiment.add_run(params={"x": 1}, id="aabbccdd")
        with run.start() as ctx:
            ctx.mark_failed("boom")
        Note.mount(ws, "Idea", body="# Idea\n")
        focus = ContextFocus(project_id=experiment.project.id, experiment_id=experiment.id)

        got = context_with_knowledge(ws, focus=focus)
        assert isinstance(got, KnowledgeContext)
        assert got.knowledge == [
            KnowledgeRef(path="knowledges/idea.md", type="Note", title="Idea", id="idea")
        ]
        assert "open_questions" not in KnowledgeContext.model_fields
        assert got.focus == focus
        plain = assemble_workspace_context(ws, focus=focus)
        for field in (
            "workspace",
            "focus",
            "projects",
            "experiments",
            "workflows",
            "recent_runs",
            "failed_runs",
            "running_runs",
            "artifacts",
            "stale_or_missing",
        ):
            assert getattr(got, field) == getattr(plain, field), field

    def test_overrides_rather_than_appends(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note.mount(ws, "Idea", body="# Idea\n")
        projected = project_knowledge(ws)
        assert len(projected) == 1
        assert len(context_with_knowledge(ws).knowledge) == len(projected)

    def test_assembly_writes_nothing(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        Note.mount(ws, "Idea", body="# Idea\n")
        before = _tree(ws)
        context_with_knowledge(ws, focus=ContextFocus(experiment_id="e"))
        assert _tree(ws) == before

    def test_raw_assembly_carries_no_knowledge_field(self, tmp_path: Path) -> None:
        plain = assemble_workspace_context(_workspace(tmp_path))

        assert not hasattr(plain, "knowledge")


class TestKnowledgeRef:
    def test_shape_and_frozen(self) -> None:
        import pydantic

        ref = KnowledgeRef(path="knowledges/idea.md", type="Note", title="Idea")

        assert ref.model_dump() == {
            "path": "knowledges/idea.md",
            "type": "Note",
            "title": "Idea",
            "id": None,
        }
        with pytest.raises(pydantic.ValidationError):
            ref.title = "other"  # type: ignore[misc]


class TestKnowledgeContext:
    def test_extends_the_workspace_read_model(self) -> None:
        assert issubclass(KnowledgeContext, WorkspaceContext)
        assert set(KnowledgeContext.model_fields) - set(WorkspaceContext.model_fields) == {
            "knowledge",
        }
        blank = KnowledgeContext(
            workspace=WorkspaceRef(id="i", name="Lab", root="r"),
            focus=ContextFocus(),
        )
        assert blank.knowledge == []
