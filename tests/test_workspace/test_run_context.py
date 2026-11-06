"""Tests for ``ExecutionContext`` (``RunContext``) — the run-execution
context manager and its register/log/checkpoint/metrics accessors.

Scope is the ExecutionContext surface only: lifecycle status resolution,
in-context result/asset/log/checkpoint/metrics I/O, working-dir guards,
and the sync/async context-manager protocols. Manifest *scanning* is owned by
``test_asset_scan`` / ``test_assets``; failure-recovery / no-op resolution by
``test_run_lifecycle_recovery``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionStatus


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

    def test_exception_lands_in_the_attempt_log_and_its_sealed_state(self, experiment):
        """The exception-propagation exit path records the failure in the two
        places an attempt has: its one log, and its own ``execution.json``."""
        run = experiment.add_run()
        ctx_ref: dict[str, object] = {}
        with pytest.raises(RuntimeError), run.start() as ctx:
            ctx_ref["ctx"] = ctx
            raise RuntimeError("detailed error")
        ctx = ctx_ref["ctx"]
        log = ctx.run_dir / "executions" / ctx.id / "run.log"
        assert log.exists()
        assert "RuntimeError" in log.read_text()
        sealed = run.executions[-1]
        assert sealed.status.value == "failed"
        assert sealed.error is not None
        assert sealed.error["type"] == "RuntimeError"


class TestRunContextResults:
    def test_set_result_then_get_result_round_trips(self, run):
        with run.start() as ctx:
            ctx.set_result("acc", 0.95)
            assert ctx.get_result("acc") == 0.95


class TestRegister:
    def test_registers_a_file(self, run):
        from molab.workspace.asset_repository import assets_produced_by
        from molab.workspace.domain import ExecutionOrigin

        with run.start() as ctx:
            dest = ctx.get_dir("work") / "nve.pt"
            dest.write_bytes(b"traj")
            asset = ctx.register(dest, title="nve.pt")
            execution_id = ctx.id
        assert asset.title == "nve.pt"
        assert isinstance(asset.origin, ExecutionOrigin)
        assert asset.origin.execution_id == execution_id
        assert asset.origin.run_id == run.id
        produced = assets_produced_by(run.experiment.project.workspace, execution_id)
        assert [item.title for item in produced] == ["nve.pt"]

    def test_same_bytes_return_the_existing_asset(self, run):
        with run.start() as ctx:
            dest = ctx.get_dir("work") / "nve.pt"
            dest.write_bytes(b"traj")
            first = ctx.register(dest, title="nve.pt")
            again = ctx.register(dest, title="nve-again.pt")
        assert again.id == first.id
        assert dest.read_bytes() == b"traj"

    def test_requires_a_title(self, run):
        with run.start() as ctx:
            with pytest.raises(ValueError, match="title"):
                ctx.register(b"traj", title=" ")
            with pytest.raises(TypeError):
                ctx.register(b"traj")  # type: ignore[call-arg]

    def test_missing_src_raises(self, run):
        with run.start() as ctx, pytest.raises(FileNotFoundError):
            ctx.register(ctx.get_dir("work") / "gone.pt", title="gone.pt")

    def test_dict_is_written_under_work(self, run):
        with run.start() as ctx:
            asset = ctx.register({"key": "value"}, title="data.json")
            written = [path for path in ctx.get_dir("work").rglob("*") if path.is_file()]
        assert asset.title == "data.json"
        assert written
        assert any(json.loads(path.read_text()) == {"key": "value"} for path in written)

    def test_path_register_keeps_the_given_title(self, run):
        with run.start() as ctx:
            src = ctx.get_dir("work") / "report.txt"
            src.write_text("ok")
            asset = ctx.register(src, title="report.txt")
        assert asset.title == "report.txt"
        assert src.read_text() == "ok"

    def test_register_metric_writes_wal_at_the_attempt_root(self, run):
        with run.start() as ctx:
            ctx.register_metric("score", 0.87, step=1)
            wal = ctx.execution_dir / "metrics.mlp.jsonl"
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
            saved = ctx.checkpoint("mid-run", data={"step": 5})
            assert saved.name == "mid-run.json"
            assert saved == ctx.get_dir("checkpoints") / "mid-run.json"
            assert "checkpoints" in saved.parts
            assert "executions" in saved.parts
            assert json.loads(saved.read_text())["data"] == {"step": 5}

    def test_checkpoints_are_distinct_paths(self, run):
        with run.start() as ctx:
            first = ctx.checkpoint("a", data={"s": 1})
            second = ctx.checkpoint("b", data={"s": 2})
            assert first != second
            assert first.name == "a.json"
            assert second.name == "b.json"


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


class TestExecutionDirectories:
    def test_every_tier_is_reached_the_same_way(self, run):
        # The point of the redesign: no directory has an accessor the others
        # lack, so a caller switching tiers changes one string.
        with run.start() as ctx:
            for name in ("work", "out", "checkpoints"):
                d = ctx.get_dir(name)
                assert d.is_dir()
                assert d.name == name
                assert d.relative_to(ctx.run_dir).parts[0] == "executions"

    def test_subdirectories_come_from_the_same_call(self, run):
        with run.start() as ctx:
            d = ctx.get_dir("out", "md")
            assert d.is_dir()
            assert d.parent.name == "out"

    def test_an_undeclared_directory_is_refused(self, run):
        from molab.workspace.execution_dirs import UnknownExecutionDirError

        # Silently creating it would make a directory nothing validates,
        # nothing versions, and no reader looks in.
        with run.start() as ctx, pytest.raises(UnknownExecutionDirError):
            ctx.get_dir("outputs")

    def test_has_dir_reports_what_is_actually_there(self, run):
        with run.start() as ctx:
            assert ctx.has_dir("checkpoints") is False
            ctx.get_dir("checkpoints")
            assert ctx.has_dir("checkpoints") is True

    def test_requires_active_execution(self, run):
        ctx = run.start()  # constructed but not entered → no execution yet
        with pytest.raises(RuntimeError, match="not been entered"):
            _ = ctx.get_dir("work")

    def test_removed_spellings_are_gone(self, run):
        with run.start() as ctx:
            # ``workdir`` was the bespoke property that made one directory
            # more equal than the rest.
            assert not hasattr(ctx, "workdir")
            assert not hasattr(ctx, "work_dir")
            assert not hasattr(ctx, "artifact")
            assert not hasattr(ctx, "folder")
            assert not hasattr(ctx, "register_asset")

    def test_the_run_record_is_written_by_its_owner(self, run, monkeypatch):
        import molab.workspace.folder as folder_mod

        seen: list[str] = []
        orig = folder_mod.write_record

        def spy(fs, directory, **kwargs: Any):
            seen.append(Path(str(directory)).name)
            return orig(fs, directory, **kwargs)

        monkeypatch.setattr(folder_mod, "write_record", spy)
        run.save()
        assert seen == [Path(str(run.run_dir)).name]
        assert not (Path(str(run.run_dir)) / "ops").exists()

    def test_register_does_not_rewrite_source(self, run):
        with run.start() as ctx:
            dest = ctx.files.put("keep.txt", "payload")
            before = dest.stat().st_mtime
            asset = ctx.register(dest, title="keep.txt")
            assert dest.read_text() == "payload"
            assert dest.stat().st_mtime == before
            assert asset.title == "keep.txt"
