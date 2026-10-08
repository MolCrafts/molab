"""Unit tests for ``molab info`` (``molab.cli.workspace.lifecycle.info``).

Spec arch-own-02e-readers: run status counts come from ``Run.status_label``
(keys ``pending`` + every ``ExecutionStatus`` value) and profile counts from
the run's latest Execution environment — never from ``run.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from molab.cli import app
from molab.profile import ProfileConfig
from molab.workspace import Workspace

_RUN_LEVEL_PROVENANCE = ("profile", "config_hash", "script", "executor_info")


def _workspace_with_record(tmp_path: Path) -> Workspace:
    """A workspace holding one run whose only provenance is a QUEUED e01."""
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
    return ws


class TestInfo:
    def test_counts_queued_run_and_its_profile(self, tmp_path: Path) -> None:
        ws = _workspace_with_record(tmp_path)

        result = CliRunner().invoke(app, ["info", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert "Queued: 1" in result.output
        assert "cpu: 1" in result.output
