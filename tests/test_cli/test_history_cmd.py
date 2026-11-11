"""``molab history push`` — the CLI is a thin shell over ``push_workspace``.

The sweep-then-push body has one home, :func:`molab.workspace.history.push_workspace`;
the CLI delegates to it and keeps its own output (``OK pushed → <remote>`` /
``Error: <git stderr>``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import molab.cli
import molab.cli.history_cmd as history_cmd
from molab.workspace import Workspace
from molab.workspace.history import GitHistory

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _workspace(root: Path) -> Path:
    Workspace(root=root, name="history-cli-lab").add_project("proj-a")
    assert GitHistory(root).init()
    return root


def _push(root: Path, remote: str) -> tuple[int, str]:
    result = CliRunner().invoke(molab.cli.app, ["history", "push", remote, "-ws", str(root)])
    return result.exit_code, " ".join(result.output.split())


class TestHistoryPush:
    def test_push_delegates_to_push_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _workspace(tmp_path / "ws")
        calls: list[tuple[str, str]] = []

        def _fake(workspace: str, remote: str) -> dict[str, str | None]:
            calls.append((workspace, remote))
            return {"commit": None, "remote": remote}

        monkeypatch.setattr(history_cmd, "push_workspace", _fake)

        exit_code, output = _push(root, "origin-x")

        assert exit_code == 0, output
        assert calls == [(str(root), "origin-x")]
        assert "OK pushed → origin-x" in output

    def test_push_to_bare_remote(self, tmp_path: Path) -> None:
        root = _workspace(tmp_path / "ws")
        remote = tmp_path / "backup.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)

        exit_code, output = _push(root, str(remote))

        assert exit_code == 0, output
        # rich wraps long paths; compare with all whitespace removed.
        assert f"OKpushed→{remote}" in "".join(output.split())

    def test_push_failure_reports_git_stderr(self, tmp_path: Path) -> None:
        root = _workspace(tmp_path / "ws")

        exit_code, output = _push(root, str(tmp_path / "missing.git"))

        assert exit_code == 1
        assert output.startswith("Error: ")
        assert "git push failed" not in output
