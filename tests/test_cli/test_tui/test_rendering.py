"""Unit tests for ``molab.cli.tui.rendering._detail_run`` (the run detail panel).

Spec arch-own-02e-readers: the panel reads status from ``Run.status_label``
and profile / config_hash / config / script / executor from the run's latest
Execution record. The fixture writes provenance only into that record;
``run.json`` carries none.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from rich.console import Console

from molab.cli.tui.rendering import _detail_execution, _detail_experiment, _detail_run
from molab.cli.tui.tree_model import TreeNode
from molab.profile import ProfileConfig
from molab.workspace import Workspace
from molab.workspace.run import Run

# Independent of ProfileConfig: sha256 over ``json.dumps({"nodes": 2},
# sort_keys=True)`` (default separators ``", "`` / ``": "``).
EXPECTED_HASH = hashlib.sha256(b'{"nodes": 2}').hexdigest()

_RUN_LEVEL_PROVENANCE = ("profile", "config_hash", "script", "executor_info")


def _run_with_record(tmp_path: Path) -> Run:
    """A run whose only provenance is the QUEUED e01 execution record."""
    ws = Workspace(tmp_path / "lab", name="Lab")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
    run._create_execution(
        profile_config=ProfileConfig({"nodes": 2}, name="cpu"),
        environment={"script": "/lab/s.py"},
        executor={"backend": "molq", "scheduler": "slurm", "scheduler_job_id": "4242"},
    )
    raw = json.loads((run.run_dir / "run.json").read_text())
    assert not any(key in raw for key in _RUN_LEVEL_PROVENANCE)
    return run


def _node(run: Run) -> TreeNode:
    return TreeNode(
        kind="run",
        node_id=("project", "p", "experiment", "e", "run", run.id),
        display_label="x",
        ref=run,
    )


def _render_text(run: Run) -> str:
    console = Console(record=True, width=200)
    for renderable in _detail_run(_node(run)):
        console.print(renderable)
    return console.export_text()


class TestDetailRun:
    def test_does_not_raise(self, tmp_path: Path) -> None:
        run = _run_with_record(tmp_path)

        body = _detail_run(_node(run))

        assert body

    def test_status_is_latest_attempt_status(self, tmp_path: Path) -> None:
        text = _render_text(_run_with_record(tmp_path))

        assert "QUEUED" in text

    def test_profile_hash_and_script_from_execution(self, tmp_path: Path) -> None:
        text = _render_text(_run_with_record(tmp_path))

        assert "cpu" in text
        assert EXPECTED_HASH[:16] in text
        assert "/lab/s.py" in text

    def test_executor_from_execution(self, tmp_path: Path) -> None:
        text = _render_text(_run_with_record(tmp_path))

        assert "slurm" in text
        assert "4242" in text

    def test_config_from_execution(self, tmp_path: Path) -> None:
        text = _render_text(_run_with_record(tmp_path))

        assert '"nodes"' in text


class TestStateStyleCoversExecutionStatuses:
    """Every ExecutionStatus a run row can show gets a style and an icon."""

    def test_queued_finalizing_interrupted_match_their_analogues(self) -> None:
        from molab.cli.tui.rendering import _STATE_STYLE, _state_icon

        for status, analogue in (
            ("queued", "pending"),
            ("finalizing", "running"),
            ("interrupted", "failed"),
        ):
            assert _STATE_STYLE.get(status) == _STATE_STYLE[analogue], status
            assert _state_icon(status) == _state_icon(analogue), status


class TestDetailExecution:
    def test_names_execution_dir_not_error_txt(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
        with pytest.raises(RuntimeError), run.start():
            raise RuntimeError("boom")
        node = TreeNode(
            kind="execution",
            node_id=("execution", "e01"),
            display_label="e01",
            ref=(run, "e01"),
        )

        console = Console(record=True, width=200, height=40)
        for item in _detail_execution(node):
            console.print(item)
        text = console.export_text()

        assert str(run.execution_dir("e01")) in text
        assert "error.txt" not in text


class TestDetailExperiment:
    def test_code_binding_rows(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        exp = ws.add_project("p").add_experiment("e")
        exp.bind_workflow("code", entrypoint="train.py:build")
        node = TreeNode(
            kind="experiment",
            node_id=("project", "p", "experiment", exp.id),
            display_label=exp.name,
            ref=exp,
        )
        console = Console(record=True, width=200, height=40)
        for item in _detail_experiment(node):
            console.print(item)
        text = console.export_text()
        assert "workflow_kind" in text
        assert "code" in text
        assert "workflow_entrypoint" in text
        assert "train.py:build" in text
        assert "task_configs" not in text

    def test_unbound_omits_both_rows(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        exp = ws.add_project("p").add_experiment("e")
        node = TreeNode(
            kind="experiment",
            node_id=("project", "p", "experiment", exp.id),
            display_label=exp.name,
            ref=exp,
        )
        console = Console(record=True, width=200, height=40)
        for item in _detail_experiment(node):
            console.print(item)
        text = console.export_text()
        assert "workflow_kind" not in text
        assert "workflow_entrypoint" not in text
