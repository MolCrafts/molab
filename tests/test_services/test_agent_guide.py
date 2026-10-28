"""``services.agent_guide`` — the AGENTS.md block is rendered from code and kept in place."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import pytest
import typer

from molab.services.agent_guide import (
    AGENT_COMMANDS,
    AGENT_PYTHON,
    BEGIN_MARKER,
    END_MARKER,
    render_agent_guide,
    splice_block,
    sync_agent_files,
)
from molab.services.workspace_check import baseline_path
from molab.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    workspace = Workspace(tmp_path / "lab", name="lab")
    workspace.materialize()
    return workspace


def _leaf(argv: list[str]) -> Any:
    """The command *argv* (after ``molab``) reaches in the CLI, or ``None``.

    typer ships its own click, so a group is recognised by its ``commands``.
    """
    from molab.cli import app

    command: Any = typer.main.get_command(app)
    for token in argv:
        children = getattr(command, "commands", None)
        if children is None:
            return command
        if token not in children:
            return None
        command = children[token]
    return None if getattr(command, "commands", None) is not None else command


class TestRender:
    def test_every_command_in_the_table_exists(self) -> None:
        for _task, line in AGENT_COMMANDS:
            argv = shlex.split(line)
            assert argv[0] == "molab"
            leaf = _leaf(argv[1:])
            assert leaf is not None, line
            options = {opt for param in leaf.params for opt in param.opts}
            flags = {token.strip("[]") for token in argv if token.lstrip("[").startswith("--")}
            assert flags <= options, (line, flags - options)

    def test_every_python_line_imports(self, ws: Workspace) -> None:
        import molab

        block = render_agent_guide(ws)
        for task, line in AGENT_PYTHON:
            module, _, names = line.partition(" import ")
            assert module == "from molab"
            for name in names.split(","):
                assert hasattr(molab, name.strip()), line
            assert f"| {task} | `{line}` |" in block

    def test_the_block_is_derived_from_the_layout_constants(self, ws: Workspace) -> None:
        block = render_agent_guide(ws)
        assert block.startswith(BEGIN_MARKER) and block.rstrip().endswith(END_MARKER)
        for name in ("scratch/", "executions/e01/", "execution.json", "knowledges/<slug>.md"):
            assert name in block
        for klass in ("Note", "Literature", "Report", "Finding", "Plan", "Observation"):
            assert f"`{klass}`" in block
        from molab.workspace.execution_dirs import list_execution_dirs

        for directory in list_execution_dirs():
            assert f"{directory.name}/" in block
        assert "index.children[].path" in block
        assert "molab validate --new-only" in block


class TestSplice:
    def test_text_outside_the_markers_is_kept(self) -> None:
        text = f"# Mine\n\nbefore\n{BEGIN_MARKER}\nold\n{END_MARKER}\nafter\n"
        out = splice_block(text, f"{BEGIN_MARKER}\nnew\n{END_MARKER}\n")
        assert out == f"# Mine\n\nbefore\n{BEGIN_MARKER}\nnew\n{END_MARKER}\nafter\n"

    def test_a_file_without_markers_gains_the_block_at_the_end(self) -> None:
        out = splice_block("# Mine\n", "B\n")
        assert out == "# Mine\n\nB\n"
        assert splice_block("", "B\n") == "B\n"


class TestSync:
    def test_sync_is_idempotent_and_preserves_user_content(self, ws: Workspace) -> None:
        root = Path(str(ws.resolve()))
        (root / "AGENTS.md").write_text("# Lab rules\n\nAsk before deleting.\n")
        (root / "CLAUDE.md").write_text("Use SI units.")

        first = sync_agent_files(ws)
        agents = (root / "AGENTS.md").read_text()
        claude = (root / "CLAUDE.md").read_text()
        second = sync_agent_files(ws)

        assert first.agents_written and first.claude_written and first.baseline_written
        assert "**/experiments/*/scratch/" in first.ignore_rules_added
        assert agents.startswith("# Lab rules\n\nAsk before deleting.\n")
        assert agents.count(BEGIN_MARKER) == 1
        assert claude == "Use SI units.\n@AGENTS.md\n"
        assert not (second.agents_written or second.claude_written or second.baseline_written)
        assert second.ignore_rules_added == ()
        assert (root / "AGENTS.md").read_text() == agents
        assert (root / "CLAUDE.md").read_text() == claude
        assert baseline_path(ws).exists()

    def test_an_existing_import_line_is_not_doubled(self, ws: Workspace) -> None:
        root = Path(str(ws.resolve()))
        (root / "CLAUDE.md").write_text("@AGENTS.md\n")
        assert not sync_agent_files(ws).claude_written
        assert (root / "CLAUDE.md").read_text() == "@AGENTS.md\n"

    def test_a_synced_workspace_validates_clean(self, ws: Workspace) -> None:
        from molab.services.workspace_check import check_workspace

        sync_agent_files(ws)
        assert check_workspace(ws).ok, check_workspace(ws).violations
