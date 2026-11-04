"""Task executors: ``thread`` (default), ``process`` and ``inline``.

A workflow chooses how its task bodies run — per workflow
(``Workflow(executor=...)``), per task (``@wf.task(executor=...)``) or per run
(``execute_run(..., executor=...)`` / ``molab run --executor``); the run wins,
then the task, then the workflow. ``process`` runs each body in a fresh
interpreter that imports this module by path and finds the task by name, so
every workflow here is defined at module level.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import threading
import time
from pathlib import Path

import pytest

import molab as me
from molab import print as molab_print
from molab.workflow import (
    RunFailedError,
    Workflow,
    WorkflowRuntime,
)
from molab.workflow.execute import execute_run

# ── module-level workflows (the process executor imports them by path) ──────

CHAIN = Workflow(name="executor-chain")


@CHAIN.task
def source(x: int) -> int:
    return x + 1


@CHAIN.task(depends_on=["source"])
def left(source: int) -> dict:
    return {"l": source * 2}


@CHAIN.task(depends_on=["source"])
def right(source: int) -> list:
    return [source, source]


@CHAIN.task(depends_on=["left", "right"])
def join(l: int, right: list) -> int:  # noqa: E741 - left's dict output binds by key
    return l + sum(right)


NAPS = Workflow(name="executor-naps")


@NAPS.task
def nap_a() -> int:
    time.sleep(0.3)
    return 1


@NAPS.task
def nap_b() -> int:
    time.sleep(0.3)
    return 2


SPIN = Workflow(name="executor-spin")


def _burn(seconds: float) -> dict:
    """Hold the GIL in a CPU loop for *seconds* of this process's CPU time."""
    start = time.time()
    t0 = time.process_time()
    total = 0
    while time.process_time() - t0 < seconds:
        total += sum(range(1000))
    return {"start": start, "end": time.time()}


@SPIN.task
def spin_root(x: int) -> int:
    return x


@SPIN.task(depends_on=["spin_root"])
def spin_a(spin_root: int) -> dict:
    return _burn(0.6)


@SPIN.task(depends_on=["spin_root"])
def spin_b(spin_root: int) -> dict:
    return _burn(0.6)


class ThreadBound:
    """Refuses use from any thread but the one that made it (like a pyo3 ``unsendable``)."""

    pickles = 0

    def __init__(self, value: int) -> None:
        self.value_ = value
        self._owner = threading.get_ident()

    def _check(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("ThreadBound used from another thread")

    def value(self) -> int:
        self._check()
        return self.value_

    def __reduce__(self) -> tuple:
        self._check()
        type(self).pickles += 1
        return (ThreadBound, (self.value_,))


BOUND = Workflow(name="executor-bound")


@BOUND.task
def make(x: int) -> ThreadBound:
    return ThreadBound(x)


@BOUND.task(depends_on=["make"])
def use(make: ThreadBound) -> int:
    return make.value() + 1


CRASH = Workflow(name="executor-crash")


@CRASH.task
def doomed(x: int) -> int:
    os.kill(os.getpid(), signal.SIGKILL)
    return x


RAISES = Workflow(name="executor-raises")


@RAISES.task
def picky(x: int) -> int:
    raise ValueError(f"bad input {x}")


SLEEPY = Workflow(name="executor-sleepy")


@SLEEPY.task
def nap(x: int) -> int:
    time.sleep(60)
    return x


EMIT = Workflow(name="executor-emit")


@EMIT.task
def emit(ctx, x: int) -> int:
    molab_print(f"hello from pid {os.getpid()}")
    ctx.metrics.scalar("loss", 0.5)
    ctx.register_artifact(b"payload", name="note.txt")
    return x


HEAL = Workflow(name="executor-heal")


@HEAL.task
def first(x: int, flag: str) -> dict:
    return {"n": x + 1, "flag": flag}


@HEAL.task(depends_on=["first"])
def second(n: int, flag: str) -> int:
    if not Path(flag).exists():
        raise RuntimeError("not healed")
    return n * 10


MIXED = Workflow(name="executor-mixed", executor="inline")


@MIXED.task
def plain(x: int) -> int:
    return x


@MIXED.task(executor="thread", depends_on=["plain"])
def threaded(plain: int) -> int:
    return plain


# ── helpers ──────────────────────────────────────────────────────────────────


def _run(tmp_path: Path, name: str = "e", params: dict | None = None):
    ws = me.Workspace(tmp_path / name, name="lab")
    return ws.add_project("p").add_experiment(name).add_run(params=params or {"x": 2})


def _records(run, execution_id: str = "e01") -> dict[str, dict]:
    doc = json.loads((run.execution_dir(execution_id) / "workflow.json").read_text())
    return {task["task_id"]: task for task in doc["task_configs"]}


def _node_records(run) -> dict[str, tuple]:
    return {
        name: (record["status"], record.get("input_refs"), record.get("output_ref"))
        for name, record in _records(run).items()
    }


# ── tests ────────────────────────────────────────────────────────────────────


class TestSameRecordsUnderEveryExecutor:
    def test_node_records_are_identical(self, tmp_path: Path) -> None:
        records = {}
        for executor in ("thread", "process", "inline"):
            run = _run(tmp_path, name=f"e-{executor}")
            result = execute_run(CHAIN, run, executor=executor)
            assert result.outputs["join"] == 12
            records[executor] = _node_records(run)
            for record in _records(run).values():
                assert record["executor"] == executor
                if executor == "process":
                    assert record["worker_pid"] != os.getpid()
                else:
                    assert record["worker_pid"] == os.getpid()
        assert records["thread"] == records["process"] == records["inline"]

    def test_unknown_executor_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="executor"):
            Workflow(name="x", executor="gpu")
        with pytest.raises(ValueError, match="executor"):
            execute_run(CHAIN, _run(tmp_path), executor="fork")


class TestParallelism:
    @staticmethod
    def _overlap(outputs: dict) -> float:
        a, b = outputs["spin_a"], outputs["spin_b"]
        return min(a["end"], b["end"]) - max(a["start"], b["start"])

    def test_process_runs_gil_bound_tasks_in_parallel(self, tmp_path: Path) -> None:
        result = execute_run(SPIN, _run(tmp_path), executor="process")
        assert self._overlap(result.outputs) > 0.2

    def test_inline_runs_one_at_a_time(self, tmp_path: Path) -> None:
        result = execute_run(SPIN, _run(tmp_path), executor="inline")
        assert self._overlap(result.outputs) <= 0


class TestThreadBoundValues:
    @pytest.mark.parametrize("executor", ["process", "inline"])
    def test_thread_bound_output_is_recorded_and_consumed(
        self, tmp_path: Path, executor: str
    ) -> None:
        ThreadBound.pickles = 0
        run = _run(tmp_path)
        result = execute_run(BOUND, run, executor=executor)
        assert result.outputs["use"] == 3
        record = _records(run)["make"]
        assert record["output_encoding"] == "pickle"
        assert "output_unrecordable" not in record
        if executor == "process":
            # The parent stores the bytes the child encoded; it never re-pickles.
            assert ThreadBound.pickles == 0


class TestFailures:
    def test_a_crashed_child_fails_its_task(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        started = time.monotonic()
        with pytest.raises(RunFailedError):
            execute_run(CRASH, run, executor="process")
        assert time.monotonic() - started < 60
        record = _records(run)["doomed"]
        assert record["status"] == "failed"
        assert "died" in record["error"]
        assert "SIGKILL" in record["error"]

    def test_a_child_exception_keeps_its_type_and_traceback(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        with pytest.raises(RunFailedError):
            execute_run(RAISES, run, executor="process")
        assert _records(run)["picky"]["error"] == "ValueError: bad input 2"
        error = run.execution("e01").error
        assert "picky" in json.dumps(error) or "bad input" in json.dumps(error)
        traceback_file = run.execution_dir("e01") / "traceback.txt"
        if traceback_file.exists():
            assert "bad input" in traceback_file.read_text()

    def test_cancelling_the_run_terminates_running_children(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        compiled = (SLEEPY).compile()

        async def scenario() -> int:
            with run.start() as ctx:
                task = asyncio.create_task(
                    WorkflowRuntime().execute(compiled, run_context=ctx, executor="process")
                )
                journal = run.execution_dir(ctx.id) / "workflow.json"
                pid = None
                deadline = time.monotonic() + 60
                while pid is None and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                    try:
                        pid = json.loads(journal.read_text())["task_configs"][0].get("worker_pid")
                    except (OSError, ValueError):
                        pid = None
                assert pid is not None
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                return pid

        pid = asyncio.run(scenario())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


class TestChildTracking:
    def test_print_metrics_and_artifacts_land_in_the_execution(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(EMIT, run, executor="process")
        execution_dir = run.execution_dir("e01")
        pid = _records(run)["emit"]["worker_pid"]
        assert f"hello from pid {pid}" in (execution_dir / "stdout.log").read_text()
        metrics = [
            json.loads(line)
            for line in (execution_dir / "artifacts" / "metrics.mlp.jsonl").read_text().splitlines()
            if line.strip()
        ]
        losses = [m for m in metrics if m.get("k") == "loss" or m.get("key") == "loss"]
        assert losses, metrics
        assert any((m.get("tags") or {}).get("task") == "emit" for m in losses)
        assert "note.txt" in {artifact.name for artifact in run.execution("e01").artifacts}


class TestRecordsDriveEveryExecutor:
    def test_rerun_one_task_under_process(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"
        run = _run(tmp_path, params={"x": 2, "flag": str(flag)})
        with pytest.raises(RunFailedError):
            execute_run(HEAL, run, executor="process")
        flag.write_text("ok")

        result = execute_run(HEAL, run, rerun=True, only=("second",), executor="process")

        assert result.outputs["second"] == 30
        records = _records(run, "e02")
        assert records["first"]["seeded_from"] == "e01"
        assert records["second"]["executor"] == "process"


class TestPrecedence:
    def test_task_overrides_workflow_and_run_overrides_both(self, tmp_path: Path) -> None:
        run = _run(tmp_path, name="defaults")
        execute_run(MIXED, run)
        records = _records(run)
        assert records["plain"]["executor"] == "inline"
        assert records["threaded"]["executor"] == "thread"

        forced = _run(tmp_path, name="forced")
        execute_run(MIXED, forced, executor="inline")
        assert {r["executor"] for r in _records(forced).values()} == {"inline"}

    def test_run_choice_is_recorded_on_the_execution(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(CHAIN, run, executor="inline", max_workers=2)
        record = run.execution("e01")
        assert record.executor["task_executor"] == "inline"
        assert record.executor["task_max_workers"] == 2


class TestRunExecuteChoosesTheExecutor:
    """``run.execute`` takes the same executor choice as ``execute_run``."""

    def test_run_execute_records_the_executor_it_was_given(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        run.execute(CHAIN, executor="inline")
        record = run.executions[-1]
        assert record.executor.get("task_executor") == "inline"

    def test_run_aexecute_takes_max_workers(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        asyncio.run(run.aexecute(CHAIN, executor="thread", max_workers=2))
        record = run.executions[-1]
        assert record.executor.get("task_executor") == "thread"
        assert record.executor.get("task_max_workers") == 2


class TestTaskTimesAreBodyTimes:
    """``started_at`` is when the body began, not when the task was launched:
    a task waiting for its turn (inline, a full pool) is ``queued_at`` only,
    so the web app's timeline shows computing time."""

    @staticmethod
    def _seconds(record: dict, start: str = "started_at") -> float:
        from datetime import datetime

        return (
            datetime.fromisoformat(record["finished_at"]) - datetime.fromisoformat(record[start])
        ).total_seconds()

    def test_inline_tasks_record_their_own_run_time(self, tmp_path: Path) -> None:
        run = _run(tmp_path, params={"k": 1})
        execute_run(NAPS, run, executor="inline")
        records = _records(run)
        from datetime import datetime

        for name in ("nap_a", "nap_b"):
            assert self._seconds(records[name]) < 0.5, (name, records[name])
            assert "queued_at" in records[name]
        # Inline bodies run one at a time: the two spans follow each other.
        spans = sorted(
            (
                datetime.fromisoformat(records[n]["started_at"]),
                datetime.fromisoformat(records[n]["finished_at"]),
            )
            for n in ("nap_a", "nap_b")
        )
        assert spans[0][1] <= spans[1][0], spans

    def test_a_one_worker_pool_records_run_time_not_wait(self, tmp_path: Path) -> None:
        run = _run(tmp_path, params={"k": 1})
        execute_run(NAPS, run, executor="thread", max_workers=1)
        records = _records(run)
        for name in ("nap_a", "nap_b"):
            assert self._seconds(records[name]) < 0.5, (name, records[name])
