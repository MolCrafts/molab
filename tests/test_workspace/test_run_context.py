"""Tests for ``ExecutionContext`` (``RunContext``) — the run-execution
context manager and its typed artifact/log/checkpoint/metrics accessors.

Scope is the ExecutionContext surface only: lifecycle status resolution,
in-context result/artifact/log/checkpoint/metrics I/O, working-dir guards,
and the sync/async context-manager protocols. Manifest *scanning* is owned by
``test_asset_scan`` / ``test_assets``; failure-recovery / no-op resolution by
``test_run_lifecycle_recovery``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molexp.workspace import Workspace
from molexp.workspace.domain import ExecutionStatus


class TestRunContextLifecycle:
    def test_enter_sets_running(self, run):
        with run.start() as ctx:
            assert run.status_summary.active == 1
            assert run.executions[-1].status is ExecutionStatus.RUNNING
            assert ctx.id

    def test_clean_exit_marks_succeeded(self, run):
        with run.start():
            pass
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED

    def test_exception_marks_failed_and_records_error(self, experiment):
        run = experiment.add_run()
        with pytest.raises(ValueError), run.start():
            raise ValueError("boom")
        state = run.executions[-1]
        assert state.status is ExecutionStatus.FAILED
        assert state.error is not None
        assert state.error["type"] == "ValueError"
        assert state.error["message"] == "boom"

    def test_exception_writes_traceback_txt(self, experiment):
        """The exception-propagation exit path lands a physical ``traceback.txt``
        trace under the execution dir (distinct from the engine-swallowed path
        owned by ``test_run_lifecycle_recovery``)."""
        run = experiment.add_run()
        ctx_ref: dict[str, object] = {}
        with pytest.raises(RuntimeError), run.start() as ctx:
            ctx_ref["ctx"] = ctx
            raise RuntimeError("detailed error")
        ctx = ctx_ref["ctx"]
        traceback_txt = ctx.run_dir / "executions" / ctx.id / "traceback.txt"
        assert traceback_txt.exists()
        assert "RuntimeError" in traceback_txt.read_text()


class TestRunContextResults:
    def test_set_result_then_get_result_round_trips(self, run):
        with run.start() as ctx:
            ctx.set_result("acc", 0.95)
            assert ctx.get_result("acc") == 0.95


class TestEmitArtifactProduct:
    def test_emits_file_and_registers_artifact(self, run):
        with run.start() as ctx:
            dest = ctx.workdir / "nve.pt"
            dest.write_bytes(b"traj")
            artifact = ctx.emit_artifact(dest, name="nve.pt")
            assert artifact.name == "nve.pt"
            names = [
                a.name for a in run._execution_repository().artifacts.list_for_execution(ctx.id)
            ]
            assert "nve.pt" in names

    def test_emitting_same_content_is_content_addressed(self, run):
        with run.start() as ctx:
            dest = ctx.workdir / "nve.pt"
            dest.write_bytes(b"traj")
            first = ctx.emit_artifact(dest, name="nve.pt")
            second = ctx.emit_artifact(dest, name="nve.pt")
            assert first.id != second.id
            assert first.content.digest == second.content.digest
            assert dest.read_bytes() == b"traj"

    def test_requires_src_or_name(self, run):
        with run.start() as ctx, pytest.raises(ValueError, match="name"):
            ctx.emit_artifact(b"traj")

    def test_missing_src_raises(self, run):
        with run.start() as ctx, pytest.raises(FileNotFoundError):
            ctx.emit_artifact(ctx.workdir / "gone.pt")


class TestEmitArtifact:
    def test_emit_artifact_writes_and_returns_readable_artifact(self, run):
        with run.start() as ctx:
            artifact = ctx.emit_artifact({"key": "value"}, name="data.json")
            assert artifact.name == "data.json"
            src = ctx.workdir / "data.json"
            assert src.exists()
            assert json.loads(src.read_text()) == {"key": "value"}

    def test_emit_artifact_from_path_defaults_name(self, run):
        with run.start() as ctx:
            src = ctx.workdir / "report.txt"
            src.write_text("ok")
            artifact = ctx.emit_artifact(src)
            assert artifact.name == "report.txt"
            assert artifact.source_path == "work/report.txt"

    def test_emit_artifact_stamps_run_and_execution_id(self, run):
        with run.start() as ctx:
            artifact = ctx.emit_artifact({"a": 1}, name="m.json")
            assert artifact.run_id == run.id
            assert artifact.execution_id == ctx.id

    def test_register_metric_writes_wal(self, run):
        with run.start() as ctx:
            ctx.register_metric("score", 0.87, step=1)
            wal = ctx.workdir / "metrics.mlp.jsonl"
            assert wal.exists()
            assert "score" in wal.read_text()


class TestLogAccessor:
    def test_append_then_tail_returns_lines(self, run):
        with run.start() as ctx:
            log = ctx.log("stdout")
            log.append("epoch 1")
            log.append("epoch 2")
            assert log.tail() == ["epoch 1", "epoch 2"]


class TestCheckpointAccessor:
    def test_checkpoint_saves_and_loads_payload(self, run):
        with run.start() as ctx:
            artifact = ctx.checkpoint("mid-run", data={"step": 5})
            assert artifact.name == "mid-run.json"
            saved = ctx.workdir / "checkpoints" / artifact.name
            assert saved.exists()
            assert "checkpoints" in saved.parts
            assert "executions" in saved.parts
            assert json.loads(saved.read_text())["data"] == {"step": 5}

    def test_checkpoints_are_distinct_artifacts(self, run):
        with run.start() as ctx:
            first = ctx.checkpoint("a", data={"s": 1})
            second = ctx.checkpoint("b", data={"s": 2})
            assert first.id != second.id
            assert first.semantic_type == "checkpoint"
            assert second.semantic_type == "checkpoint"


class TestTaskWorkdir:
    def test_task_workdir_creates_missing_dir(self, run):
        with run.start() as ctx:
            data_dir = ctx.task_workdir("qm9")
            assert data_dir.is_dir()
            assert isinstance(data_dir, Path)

    def test_execution_id_requires_entered_context(self, run):
        ctx = run.start()  # constructed but not entered → no execution yet
        with pytest.raises(RuntimeError, match="not been entered"):
            _ = ctx.id


class TestAsyncRunContext:
    """``async with run.start()`` protocol + the ``with run as ctx`` sugar."""

    @pytest.mark.asyncio
    async def test_async_with_start_marks_running_then_succeeded(self, tmp_path):
        ws = Workspace(root=tmp_path, name="ws")
        run = ws.add_project(name="p").add_experiment(name="e").add_run()
        async with run.start() as ctx:
            assert ctx.run_dir.exists()
            assert run.executions[-1].status is ExecutionStatus.RUNNING
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED

    def test_run_as_context_manager_sugar_succeeds(self, tmp_path):
        ws = Workspace(root=tmp_path, name="ws")
        run = ws.add_project(name="p").add_experiment(name="e").add_run()
        with run as ctx:
            assert ctx.run_dir.exists()
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED


class TestRunContextWorkdir:
    def test_workdir_is_under_execution_work(self, run):
        with run.start() as ctx:
            d = ctx.workdir
            assert d.is_dir()
            assert d.name == "work"
            assert d.relative_to(ctx.run_dir).parts[0] == "executions"

    def test_requires_active_execution(self, run):
        ctx = run.start()  # constructed but not entered → no execution yet
        with pytest.raises(RuntimeError, match="not been entered"):
            _ = ctx.workdir

    def test_removed_spellings_are_gone(self, run):
        with run.start() as ctx:
            assert not hasattr(ctx, "work_dir")
            assert not hasattr(ctx, "artifact")
            assert not hasattr(ctx, "folder")
            assert not hasattr(ctx, "register_asset")

    def test_platform_json_writes_go_through_filestore(self, run, monkeypatch):
        from molexp.workspace.file_store import FileStore

        seen: list[str] = []
        orig = FileStore.put

        def spy(self, relpath, data):
            seen.append(Path(relpath).as_posix())
            return orig(self, relpath, data)

        monkeypatch.setattr(FileStore, "put", spy)
        run.save()
        assert "run.json" in seen
        assert "ops/run.json" not in seen

    def test_emit_artifact_does_not_rewrite_source(self, run):
        with run.start() as ctx:
            dest = ctx.files.put("keep.txt", "payload")
            before = dest.stat().st_mtime
            artifact = ctx.emit_artifact(dest, name="keep.txt")
            assert dest.read_text() == "payload"
            assert dest.stat().st_mtime == before
            assert artifact.name == "keep.txt"
