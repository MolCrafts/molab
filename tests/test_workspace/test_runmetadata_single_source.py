"""``RunMetadata`` is the single source of run hot state (persist-one-02).

``status`` / ownership / ``execution_history`` live on ``run.json``. Heartbeat
is the run-root ``alive`` mtime — not ``heartbeat_at`` / ``labels``. ``ops/``
and ``_ops/`` are not written.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace.domain import ExecutionStatus
from molab.workspace.models import RunMetadata, RunStatus


def _read_run_json(run) -> dict:
    return json.loads(Path(str(run.run_dir / "run.json")).read_text())


def _ops_dirs(run) -> tuple[Path, Path]:
    root = Path(str(run.run_dir))
    return root / "ops", root / "_ops"


class TestRunMetadata:
    def test_hot_state_fields_are_model_fields(self) -> None:
        fields = RunMetadata.model_fields
        for name in (
            "status",
            "owner_pid",
            "owner_host",
            "started_at",
            "finished_at",
        ):
            assert name in fields, f"{name!r} must live on RunMetadata"

    def test_heartbeat_at_and_labels_are_not_model_fields(self) -> None:
        fields = RunMetadata.model_fields
        assert "heartbeat_at" not in fields
        assert "labels" not in fields

    def test_legacy_heartbeat_at_and_labels_are_ignored(self) -> None:
        meta = RunMetadata.model_validate(
            {
                "id": "r",
                "status": "failed",
                "definition_hash": "h",
                "experiment_revision_id": "rev",
                "heartbeat_at": "2026-01-01T00:00:00",
                "labels": {"pid": "1", "host": "h"},
            }
        )
        assert meta.id == "r"
        assert meta.status == RunStatus.FAILED
        assert not hasattr(meta, "heartbeat_at")
        assert not hasattr(meta, "labels")

    def test_cancel_and_lifecycle_write_execution_json_not_ops(self, run) -> None:
        ops, legacy = _ops_dirs(run)
        with run.start() as ctx:
            on_disk = _read_run_json(run)
            # Operational hot state no longer lives on run.json.
            assert "status" not in on_disk
            assert "owner_pid" not in on_disk
            assert "owner_host" not in on_disk
            assert not ops.exists()
            assert not legacy.exists()
            exec_json = json.loads(
                (Path(str(run.run_dir)) / "executions" / ctx.id / "execution.json").read_text()
            )
            assert exec_json["status"] == "running"

        after = _read_run_json(run)
        assert "status" not in after
        assert "owner_pid" not in after
        assert "owner_host" not in after
        assert not ops.exists()
        assert not legacy.exists()
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED

        other = run.experiment.add_run(params={"lr": 2e-4})
        with other.start() as other_ctx:
            other.cancel(other_ctx.id)
        cancelled = _read_run_json(other)
        assert "status" not in cancelled
        assert "finished_at" not in cancelled
        assert "owner_pid" not in cancelled
        assert "owner_host" not in cancelled
        other_ops, other_legacy = _ops_dirs(other)
        assert not other_ops.exists()
        assert not other_legacy.exists()
        assert other.executions[-1].status is ExecutionStatus.CANCELLED
        assert other.executions[-1].finished_at is not None

    def test_failed_lifecycle_writes_error_and_status_to_execution_json(self, run) -> None:
        try:
            with run.start():
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        on_disk = _read_run_json(run)
        assert "status" not in on_disk
        assert "error" not in on_disk
        state = run.executions[-1]
        assert state.status is ExecutionStatus.FAILED
        assert state.error is not None
        assert state.error["type"] == "RuntimeError"
        assert state.error["message"] == "boom"
        ops, legacy = _ops_dirs(run)
        assert not ops.exists()
        assert not legacy.exists()


class TestUpdateProvenance:
    def test_update_provenance_persists_submit_fields(self, run) -> None:
        run.materialize()
        run.update_provenance(
            script="/tmp/wf.py",
            submit_cwd="/tmp",
            profile="cpu",
            config={"cpus": 8},
            config_hash="abc",
            executor_info={"backend": "molq", "scheduler": "slurm"},
        )
        # The deprecated in-memory compatibility shell retains submit fields.
        assert run.metadata.script == "/tmp/wf.py"
        assert run.metadata.submit_cwd == "/tmp"
        assert run.metadata.profile == "cpu"
        assert run.metadata.config == {"cpus": 8}
        assert run.metadata.executor_info["scheduler"] == "slurm"
        # …but run.json persists only the logical definition fields.
        on_disk = _read_run_json(run)
        assert "script" not in on_disk
        assert "submit_cwd" not in on_disk
        assert "profile" not in on_disk
        assert "config" not in on_disk
        assert "config_hash" not in on_disk
        assert "executor_info" not in on_disk
