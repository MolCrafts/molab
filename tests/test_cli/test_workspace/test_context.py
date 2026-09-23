"""``molab context`` consumes the services knowledge projection.

knowledge-crossref-07: the CLI defines no projection of its own — it hands the
complete ``WorkspaceContext`` from ``molab.services.knowledge_context`` to
``_render``, so the printed rows stay what the server's ``GET /context``
reports. Goldens are the **file form** (D17): a Note lands as
``knowledges/<name>.md``, never a directory holding ``note.json``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from typer.testing import CliRunner

from molab.cli import app
from molab.cli.workspace import context as context_cmd
from molab.knowledge import Note
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace
from molab.workspace.workspace_context import WorkspaceContext

_COOLING_RATE_ROW = (
    "projects/p/experiments/e/knowledges/cooling-rate.md",
    "Note",
    "Cooling rate",
    "cooling-rate",
)


def _with_note(tmp_path: Path, name: str, text: str) -> Workspace:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    experiment = ws.add_project("p").add_experiment("e")
    write_knowledge(
        experiment,
        name=name,
        of=Note,
        sources=[],
        created_by="cli",
        text=text,
    )
    return ws


def _files(root: Path) -> set[str]:
    """Every path under *root* except the git store — the write detector."""
    return {
        str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.relative_to(root).parts
    }


def _record(monkeypatch: pytest.MonkeyPatch) -> list[WorkspaceContext]:
    seen: list[WorkspaceContext] = []
    monkeypatch.setattr(context_cmd, "_render", seen.append)
    return seen


def _rows(recorded: WorkspaceContext) -> list[tuple[str, str, str, str | None]]:
    return [(ref.path, ref.type, ref.title, ref.id) for ref in recorded.knowledge]


class TestContextConsumesProjection:
    def test_reads_the_services_projection(self) -> None:
        src = inspect.getsource(context_cmd)
        assert "context_with_knowledge" in src
        assert "molab.services.knowledge_context" in src

    def test_defines_no_second_projection(self) -> None:
        src = inspect.getsource(context_cmd)
        assert "project_knowledge" not in src
        assert "model_copy" not in src


class TestContextRendersKnowledgeRows:
    def test_records_the_projected_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = _with_note(tmp_path, "cooling-rate", "# Cooling rate\n\nQuenched at 100 K/ps.\n")
        seen = _record(monkeypatch)

        result = CliRunner().invoke(app, ["context", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert len(seen) == 1
        assert _rows(seen[0]) == [_COOLING_RATE_ROW]

    def test_prints_the_knowledge_count(self, tmp_path: Path) -> None:
        ws = _with_note(tmp_path, "cooling-rate", "# Cooling rate\n\nQuenched at 100 K/ps.\n")

        result = CliRunner().invoke(app, ["context", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert "knowledge:   1" in result.stdout

    def test_empty_workspace_projects_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        seen = _record(monkeypatch)

        result = CliRunner().invoke(app, ["context", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert seen[0].knowledge == []

    def test_title_falls_back_to_the_document_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = _with_note(tmp_path, "no-heading", "plain prose, no H1\n")
        seen = _record(monkeypatch)

        result = CliRunner().invoke(app, ["context", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert _rows(seen[0]) == [
            (
                "projects/p/experiments/e/knowledges/no-heading.md",
                "Note",
                "no-heading",
                "no-heading",
            )
        ]

    def test_the_projection_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = _with_note(tmp_path, "cooling-rate", "# Cooling rate\n\nQuenched at 100 K/ps.\n")
        _record(monkeypatch)
        before = _files(Path(str(ws.root)))

        result = CliRunner().invoke(app, ["context", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert _files(Path(str(ws.root))) == before
