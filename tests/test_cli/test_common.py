"""Unit tests for the run readers in ``molab.cli._common``.

Spec arch-own-02e-readers: ``run_environment`` / ``run_executor_info`` read
the run's **latest** Execution record (``execution.json``) — never
``run.json``. The fixture writes provenance only into the attempt record, so
a reader that still consults ``run.json`` sees nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from molab.profile import ProfileConfig
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.experiment import Experiment
from molab.workspace.run import Run

# Independent of ProfileConfig: sha256 over ``json.dumps({"nodes": 2},
# sort_keys=True)`` (default separators ``", "`` / ``": "``).
EXPECTED_HASH = hashlib.sha256(b'{"nodes": 2}').hexdigest()

_RUN_LEVEL_PROVENANCE = ("profile", "config_hash", "script", "executor_info")


def _experiment(tmp_path: Path) -> Experiment:
    ws = Workspace(tmp_path / "lab", name="Lab")
    ws.materialize()
    return ws.add_project("p").add_experiment("e")


def _run_with_record(tmp_path: Path) -> Run:
    """A run whose only provenance is the QUEUED e01 execution record."""
    run = _experiment(tmp_path).add_run(params={"x": 1})
    run.create_execution(
        profile_config=ProfileConfig({"nodes": 2}, name="cpu"),
        environment={"script": "/lab/s.py"},
        executor={"backend": "molq", "scheduler": "slurm", "scheduler_job_id": "4242"},
    )
    raw = json.loads((run.run_dir / "run.json").read_text())
    assert not any(key in raw for key in _RUN_LEVEL_PROVENANCE)
    return run


class TestRunEnvironment:
    def test_returns_latest_execution_environment(self, tmp_path: Path) -> None:
        from molab.cli._common import run_environment

        run = _run_with_record(tmp_path)

        env = run_environment(run)

        assert env["profile"] == "cpu"
        assert env["config_hash"] == EXPECTED_HASH
        assert env["config"] == {"nodes": 2}
        assert env["script"] == "/lab/s.py"

    def test_no_execution_returns_empty(self, tmp_path: Path) -> None:
        from molab.cli._common import run_environment

        run = _experiment(tmp_path).add_run(params={"x": 1})

        assert run_environment(run) == {}

    def test_latest_attempt_wins(self, tmp_path: Path) -> None:
        from molab.cli._common import run_environment

        run = _run_with_record(tmp_path)
        run.cancel("e01")
        run.create_execution(
            mode=ExecutionMode.RERUN,
            based_on_execution_id="e01",
            profile_config=ProfileConfig({}, name="gpu"),
        )

        assert run_environment(run)["profile"] == "gpu"

    def test_returned_dict_is_a_copy(self, tmp_path: Path) -> None:
        from molab.cli._common import run_environment

        run = _run_with_record(tmp_path)

        first = run_environment(run)
        first["profile"] = "mutated"
        first["extra"] = "added"

        second = run_environment(run)
        assert second["profile"] == "cpu"
        assert "extra" not in second


class TestRunExecutorInfo:
    def test_reads_latest_execution_executor(self, tmp_path: Path) -> None:
        from molab.cli._common import run_executor_info

        run = _run_with_record(tmp_path)

        info = run_executor_info(run)

        assert info["scheduler"] == "slurm"
        assert info["scheduler_job_id"] == "4242"
        assert info["backend"] == "molq"

    def test_no_execution_returns_empty(self, tmp_path: Path) -> None:
        from molab.cli._common import run_executor_info

        run = _experiment(tmp_path).add_run(params={"x": 1})

        assert run_executor_info(run) == {}
