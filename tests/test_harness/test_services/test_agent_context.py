"""The mount context renders knowledge through the services projection.

``build_mount_context`` is the knowledge projection's third consumer. Once the
producer lives in ``molab.services`` (D10), a bare ``workspace.context()``
carries ``knowledge == []`` and the ``## Knowledge`` section would silently
empty out — so the mount context takes its read-model from
``molab.services.knowledge_context``.
"""

from __future__ import annotations

from pathlib import Path

from molab.harness.services import agent_context
from molab.harness.services.agent_context import build_mount_context, mount_session_scope
from molab.knowledge import mount_note
from molab.services.knowledge_context import context_with_knowledge
from molab.workspace import Workspace


def _workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="Lab")
    ws.materialize()
    return ws


def _disk_files(ws: Workspace) -> set[str]:
    """Every workspace file except the git history (history is not the block)."""
    return {
        str(p.relative_to(ws.root))
        for p in Path(ws.root).rglob("*")
        if p.is_file() and ".git" not in p.parts
    }


class TestMountContextKnowledge:
    def test_knowledge_section_renders_the_projected_row(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        mount_note(ws, "Idea", body="# Idea\n")

        block = build_mount_context(ws)

        assert "## Knowledge" in block
        assert "- Idea (knowledges/idea.md)" in block

    def test_read_model_comes_from_the_services_projection(self) -> None:
        assert agent_context.context_with_knowledge is context_with_knowledge

    def test_no_scope_still_renders_the_workspace_sections_without_writing(
        self, tmp_path: Path
    ) -> None:
        ws = _workspace(tmp_path)
        mount_note(ws, "Idea", body="# Idea\n")
        before = _disk_files(ws)

        block = build_mount_context(ws)

        assert block.startswith("# Mounted on workspace `Lab`")
        assert _disk_files(ws) == before, "the mount context must not persist its focus"

        # The scoped entry point returns no block and no anchor for no scope.
        assert mount_session_scope(ws) == ("", None)
