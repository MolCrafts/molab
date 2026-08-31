"""``RunMetadata`` is the single source of run hot state (persist-one-02).

``status`` / ownership / ``execution_history`` live on ``run.json``. Heartbeat
is the run-root ``alive`` mtime — not ``heartbeat_at`` / ``labels``. ``ops/``
and ``_ops/`` are not written.
"""

from __future__ import annotations

import json
from pathlib import Path

from molexp.workspace.models import RunMetadata, RunStatus


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
            "current_execution_id",
            "execution_history",
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
                "heartbeat_at": "2026-01-01T00:00:00",
                "labels": {"pid": "1", "host": "h"},
            }
        )
        assert meta.id == "r"
        assert meta.status == RunStatus.FAILED
        assert not hasattr(meta, "heartbeat_at")
        assert not hasattr(meta, "labels")

    def test_cancel_and_lifecycle_write_run_json_not_ops(self, run) -> None:
        ops, legacy = _ops_dirs(run)
        with run.start():
            on_disk = _read_run_json(run)
            assert on_disk["status"] == "running"
            assert on_disk["owner_pid"] is not None
            assert on_disk["owner_host"] is not None
            assert not ops.exists()
            assert not legacy.exists()

        after = _read_run_json(run)
        assert after["status"] == "succeeded"
        assert after["owner_pid"] is None
        assert after["owner_host"] is None
        assert not ops.exists()
        assert not legacy.exists()

        other = run.experiment.add_run(params={"lr": 2e-4})
        other.materialize()
        other.cancel()
        cancelled = _read_run_json(other)
        assert cancelled["status"] == "cancelled"
        assert cancelled["finished_at"] is not None
        assert cancelled["owner_pid"] is None
        assert cancelled["owner_host"] is None
        other_ops, other_legacy = _ops_dirs(other)
        assert not other_ops.exists()
        assert not other_legacy.exists()
        assert other.status == "cancelled"

    def test_failed_lifecycle_writes_error_and_status_to_run_json(self, run) -> None:
        try:
            with run.start():
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        on_disk = _read_run_json(run)
        assert on_disk["status"] == "failed"
        assert on_disk["error"] is not None
        assert on_disk["error"]["type"] == "RuntimeError"
        assert run.metadata.error is not None
        assert run.metadata.error.message == "boom"
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
        assert run.metadata.script == "/tmp/wf.py"
        assert run.metadata.submit_cwd == "/tmp"
        assert run.metadata.profile == "cpu"
        assert run.metadata.config == {"cpus": 8}
        assert run.metadata.executor_info["scheduler"] == "slurm"
        on_disk = _read_run_json(run)
        assert on_disk["script"] == "/tmp/wf.py"
        assert on_disk["executor_info"]["scheduler"] == "slurm"
