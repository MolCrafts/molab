"""Unit tests for ``molab.workspace.execution_context`` (``ExecutionContext``).

The public context for one physical Execution of a logical Run
(``RunContext`` is its alias).

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the heartbeat merge: the per-Execution ``alive`` file is
driven through ``molab.workspace.run_heartbeat`` (``touch_alive`` /
``unlink_alive``), i.e. through the workspace ``FileSystem`` — there is no
second raw-``pathlib`` heartbeat implementation on the context.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionStatus
from molab.workspace.execution_context import ExecutionContext
from molab.workspace.fs_local import LocalFileSystem
from tests.support.counting_fs import CountingFileSystem


class TestExecutionContextHeartbeat:
    def test_alive_goes_through_workspace_fs(self, tmp_path: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})
        fs.reset()

        with run.start() as ctx:
            execution_id = ctx.id
            assert fs.for_basename("alive", "touch") == 1
            assert fs.for_basename("alive", "remove") == 0

        assert fs.for_basename("alive", "remove") == 1
        assert execution_id == "e01"
        assert not (Path(str(run.run_dir)) / "executions" / "e01" / "alive").exists()

    def test_failed_alive_remove_still_seals(self, tmp_path: Path) -> None:
        # A remote workspace can fail to remove ``alive``; that is a stale
        # heartbeat file, never a reason to skip the seal.
        fs = _AliveRemoveFails(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})

        with run.start() as ctx:
            execution_id = ctx.id

        assert fs.for_basename("alive", "remove") == 1
        assert execution_id == "e01"
        [execution] = run.executions
        assert execution.status is ExecutionStatus.SUCCEEDED
        assert execution.sealed

    def test_failed_alive_remove_does_not_mask_body_error(self, tmp_path: Path) -> None:
        fs = _AliveRemoveFails(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})

        with pytest.raises(RuntimeError, match="body failed"), run.start():
            raise RuntimeError("body failed")

        [execution] = run.executions
        assert execution.status is ExecutionStatus.FAILED
        assert execution.sealed

    def test_heartbeat_loop_survives_touch_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace import execution_context as ctx_mod

        ws = Workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})
        calls: list[int] = []

        def flaky_touch(_run: object, _execution_id: str) -> None:
            calls.append(1)
            if len(calls) == 1:
                raise OSError("remote touch failed")

        with run.start() as ctx:
            # Patched after entry: the context's own heartbeat thread is
            # already parked on the real 30 s interval; drive a second loop.
            monkeypatch.setattr(ctx_mod, "touch_alive", flaky_touch)
            monkeypatch.setattr(ctx_mod, "HEARTBEAT_INTERVAL_SECONDS", 0.001)
            stop = threading.Event()
            worker = threading.Thread(target=ctx._heartbeat_loop, args=(stop,), daemon=True)
            worker.start()
            deadline = time.monotonic() + 5
            while len(calls) < 3 and time.monotonic() < deadline:
                time.sleep(0.005)
            stop.set()
            worker.join(timeout=5)
        assert len(calls) >= 3

    def test_private_path_helper_removed(self) -> None:
        assert not hasattr(ExecutionContext, "_heartbeat_path")


class _AliveRemoveFails(CountingFileSystem):
    """Counting wrapper whose ``remove`` of the ``alive`` file raises."""

    def remove(self, path: object, *args: object, **kwargs: object) -> None:
        if str(path).rsplit("/", 1)[-1] == "alive":
            self.calls["remove"] += 1
            self.by_basename[("remove", "alive")] += 1
            raise OSError("remote remove failed")
        self._wrap("remove", self._inner.remove)(path, *args, **kwargs)
