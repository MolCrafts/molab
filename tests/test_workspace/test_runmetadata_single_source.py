"""``run.json`` holds only a run's logical definition.

Attempt status, ownership, time, and error live on the Execution record.
Heartbeat is the per-Execution ``alive`` mtime — not ``heartbeat_at`` /
``labels``. ``ops/`` and ``_ops/`` are not written.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import molab.workspace
import molab.workspace.models as workspace_models
from molab.workspace.domain import ExecutionStatus
from molab.workspace.models import RunMetadata


def _read_run_json(run) -> dict:
    return json.loads(Path(str(run.run_dir / "run.json")).read_text(encoding="utf-8"))


def _ops_dirs(run) -> tuple[Path, Path]:
    root = Path(str(run.run_dir))
    return root / "ops", root / "_ops"


_PROVENANCE_FIELDS = (
    "script",
    "source_snapshot",
    "submit_cwd",
    "profile",
    "config",
    "config_hash",
    "executor_info",
)

_EXECUTION_ERA_FIELDS = frozenset(
    {"status", "owner_pid", "owner_host", "started_at", "finished_at", "error"}
)


def _execution_era_metadata_reads(source: str) -> list[str]:
    """``x.metadata.<era>`` and ``getattr(x.metadata, "<era>", ...)`` in *source*."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _EXECUTION_ERA_FIELDS
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "metadata"
        ):
            hits.append(f"{node.lineno}:{node.attr}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Attribute)
            and node.args[0].attr == "metadata"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _EXECUTION_ERA_FIELDS
        ):
            hits.append(f"{node.lineno}:{node.args[1].value}")
    return hits


class TestRunMetadata:
    def test_execution_era_fields_are_not_model_fields(self) -> None:
        fields = RunMetadata.model_fields
        for name in (
            "status",
            "owner_pid",
            "owner_host",
            "started_at",
            "finished_at",
            "error",
        ):
            assert name not in fields, f"{name!r} lives on the Execution record"

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
        assert not hasattr(meta, "status")
        assert not hasattr(meta, "heartbeat_at")
        assert not hasattr(meta, "labels")

    def test_legacy_execution_era_dict_is_ignored(self) -> None:
        meta = RunMetadata.model_validate(
            {
                "id": "r",
                "definition_hash": "h",
                "experiment_revision_id": "rev",
                "status": "failed",
                "owner_pid": 1,
                "owner_host": "h",
                "started_at": "2026-01-01T00:00:00",
                "finished_at": None,
                "error": {
                    "type": "X",
                    "message": "m",
                    "timestamp": "2026-01-01T00:00:00",
                },
            }
        )
        assert meta.id == "r"
        for name in _EXECUTION_ERA_FIELDS:
            assert not hasattr(meta, name)

    def test_no_reader_of_execution_era_fields(self) -> None:
        assert _execution_era_metadata_reads("run.metadata.error")
        assert _execution_era_metadata_reads('getattr(run.metadata, "status", None)')
        assert _execution_era_metadata_reads("rec.finished_at") == []
        assert _execution_era_metadata_reads("run.metadata.parameters") == []

        src = Path(__file__).resolve().parents[2] / "src" / "molab"
        scanned = sorted(path for path in src.rglob("*.py") if "__pycache__" not in path.parts)
        assert scanned
        offenders = [
            f"{path.relative_to(src.parents[1])}:{hit}"
            for path in scanned
            for hit in _execution_era_metadata_reads(path.read_text(encoding="utf-8"))
        ]
        assert offenders == []

    def test_error_info_is_gone(self) -> None:
        assert not hasattr(molab.workspace, "ErrorInfo")
        assert not hasattr(workspace_models, "ErrorInfo")

    def test_execution_provenance_fields_are_not_model_fields(self) -> None:
        fields = RunMetadata.model_fields
        for name in _PROVENANCE_FIELDS:
            assert name not in fields, f"{name!r} lives on the Execution record"

    def test_legacy_provenance_keys_are_ignored(self) -> None:
        meta = RunMetadata.model_validate(
            {
                "id": "r",
                "definition_hash": "h",
                "experiment_revision_id": "rev",
                "script": "/x.py",
                "source_snapshot": {"dir": "source"},
                "submit_cwd": "/tmp",
                "profile": "cpu",
                "config": {"cpus": 8},
                "config_hash": "abc",
                "executor_info": {"job_id": "j"},
            }
        )
        assert meta.id == "r"
        for name in _PROVENANCE_FIELDS:
            assert not hasattr(meta, name)

    def test_run_has_no_update_provenance(self, run) -> None:
        assert not hasattr(run, "update_provenance")

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
