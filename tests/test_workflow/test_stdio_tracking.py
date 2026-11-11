"""Workflow tasks and the current execution's stdio (D92).

The engine runs inside an ``ExecutionContext``, so ``molab.print`` in a task
body — sync (``asyncio.to_thread``) or async — lands in that execution's
``stdout.log``, and ``tracking.current_task()`` names the task even when
same-level tasks run in parallel. ``CommandTask`` appends its child's
captured streams to the same files.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

import molab
from molab import print
from molab.workflow import CommandError, CommandTask, Workflow, WorkflowResult
from molab.workspace import tracking
from molab.workspace.run import Run

_LINES = 200


def _make_runs(tmp_path: Path, n: int = 1) -> list[Run]:
    ws = molab.Workspace(tmp_path / "ws", name="lab")
    exp = ws.add_project("demo").add_experiment("stdio")
    return [exp.add_run(params={"i": i}) for i in range(n)]


def _parallel_printers() -> Workflow:
    """Four same-level tasks, two sync and two async, each printing 200 lines."""
    wf = Workflow(name="printers")

    def _sync_body(name: str) -> dict[str, str | None]:
        seen = tracking.current_task()
        for n in range(_LINES):
            print(f"{name} line {n} " + "z" * 40)
        return {"task": seen, "after": tracking.current_task()}

    async def _async_body(name: str) -> dict[str, str | None]:
        seen = tracking.current_task()
        for n in range(_LINES):
            print(f"{name} line {n} " + "z" * 40)
            if n % 20 == 0:
                await asyncio.sleep(0)
        return {"task": seen, "after": tracking.current_task()}

    @wf.task
    def sync_a(i: int) -> dict[str, str | None]:
        return _sync_body("sync_a")

    @wf.task
    def sync_b(i: int) -> dict[str, str | None]:
        return _sync_body("sync_b")

    @wf.task
    async def async_a(i: int) -> dict[str, str | None]:
        return await _async_body("async_a")

    @wf.task
    async def async_b(i: int) -> dict[str, str | None]:
        return await _async_body("async_b")

    return wf


_TASKS = ("sync_a", "sync_b", "async_a", "async_b")


def _expected(task: str) -> list[str]:
    return [f"{task} line {n} " + "z" * 40 for n in range(_LINES)]


def _assert_complete_lines(stdout_log: Path) -> None:
    lines = stdout_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(_TASKS) * _LINES
    for task in _TASKS:
        assert [line for line in lines if line.startswith(f"{task} ")] == _expected(task)


class TestParallelTasks:
    def test_every_line_whole_and_task_scoped(self, tmp_path: Path, capsys) -> None:
        (run,) = _make_runs(tmp_path)
        result = run.execute(_parallel_printers())
        assert isinstance(result, WorkflowResult)
        capsys.readouterr()
        for task in _TASKS:
            assert result.outputs[task] == {"task": task, "after": task}
        assert tracking.current_task() is None
        assert tracking.current() is None
        _assert_complete_lines(run.execution_dir("e01") / "stdout.log")

    def test_two_executions_in_one_loop_stay_apart(self, tmp_path: Path, capsys) -> None:
        runs = _make_runs(tmp_path, 2)

        async def both() -> None:
            await asyncio.gather(*(run.aexecute(_parallel_printers()) for run in runs))

        asyncio.run(both())
        capsys.readouterr()
        for run in runs:
            _assert_complete_lines(run.execution_dir("e01") / "stdout.log")


class TestCommandTask:
    def _wf(self, argv: list[str]) -> Workflow:
        wf = Workflow(name="command")
        wf.add(CommandTask(argv), name="cmd")
        return wf

    def test_child_output_lands_in_stdio_logs(self, tmp_path: Path) -> None:
        (run,) = _make_runs(tmp_path)
        argv = [
            sys.executable,
            "-c",
            "import sys; print('child out'); sys.stderr.write('child err')",
        ]
        result = run.execute(self._wf(argv))
        assert isinstance(result, WorkflowResult)
        assert result.outputs["cmd"].stdout == "child out\n"
        exec_dir = run.execution_dir("e01")
        assert (exec_dir / "stdout.log").read_text(encoding="utf-8") == "child out\n"
        assert (exec_dir / "stderr.log").read_text(encoding="utf-8") == "child err\n"

    @pytest.mark.asyncio
    async def test_failing_child_is_recorded_too(self, tmp_path: Path) -> None:
        (run,) = _make_runs(tmp_path)
        argv = [sys.executable, "-c", "import sys; sys.stderr.write('bad\\n'); sys.exit(2)"]
        with run.start() as ctx, pytest.raises(CommandError):
            await CommandTask(argv).execute(None)  # ty: ignore[invalid-argument-type]
        assert (ctx.execution_dir / "stderr.log").read_text(encoding="utf-8") == "bad\n"

    @pytest.mark.asyncio
    async def test_outside_an_execution_writes_nothing(self, tmp_path: Path) -> None:
        out = await CommandTask([sys.executable, "-c", "print('x')"]).execute(None)  # ty: ignore[invalid-argument-type]
        assert out.stdout == "x\n"
        assert tracking.current() is None
