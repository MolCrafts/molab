"""One-step tracked execution — ``execution.execute`` / ``Run.execute``.

``execution.execute(workflow)`` starts a queued attempt.
``run.execute(workflow)`` allocates the attempt and then runs it. Both reuse
the ``molab run`` path: RunContext lifecycle (status machine, heartbeat) plus
the workflow engine. ``Run.execute`` reaches the engine through the
``set_run_executor`` inversion seam (workspace never imports workflow).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import molab as me
from molab.profile import ProfileConfig
from molab.workflow import (
    RunFailedError,
    RunNotExecutableError,
    Workflow,
    WorkflowCompiler,
    WorkflowRecoveryError,
    WorkflowResult,
    default_binding_registry,
)
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.run import Run
from tests.support.journal import poison_node_output


def _make_run(tmp_path: Path, params: dict | None = None):
    ws = me.Workspace(tmp_path / "ws", name="lab")
    exp = ws.add_project("demo").add_experiment("pipeline")
    return exp.add_run(params=params if params is not None else {"x": 3})


_CONSTANT_ADD = {
    "name": "constant_add",
    "task_configs": [
        {"task_id": "a", "task_type": "core.constant", "config": {"value": 2}, "status": "pending"},
        {"task_id": "b", "task_type": "core.constant", "config": {"value": 3}, "status": "pending"},
        {"task_id": "c", "task_type": "core.add", "config": {}, "status": "pending"},
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}


def _build_wf() -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def double(x: int) -> int:
        return x * 2

    @wf.task(depends_on=["double"])
    def summarize(double: int) -> str:
        return f"got {double}"

    return wf


def _healing_wf(flag: Path) -> Workflow:
    wf = Workflow(name="healing")

    @wf.task
    def stage_a(x: int) -> int:
        return x + 1

    @wf.task(depends_on=["stage_a"])
    def stage_b(stage_a: int) -> int:
        if not Path(str(flag)).exists():
            raise RuntimeError("not healed yet")
        return stage_a * 100

    return wf


def _execute_run(
    workflow: Workflow,
    run: Run,
    *,
    resume: bool = False,
    rerun: bool = False,
    fresh: bool = False,
    profile_config: ProfileConfig | None = None,
    execution_id: str | None = None,
) -> WorkflowResult:
    from molab.workflow.execute import execute_run

    result = execute_run(
        workflow,
        run,
        resume=resume,
        rerun=rerun,
        fresh=fresh,
        profile_config=profile_config,
        execution_id=execution_id,
    )
    if not isinstance(result, WorkflowResult):
        raise TypeError(f"execute_run returned {type(result).__name__}")
    return result


class _Collect:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def handle(self, record: object) -> None:
        message = getattr(record, "message", None)
        self.messages.append(message if isinstance(message, str) else str(record))


def _capture_execute_logs(
    fn: Callable[[], WorkflowResult],
) -> tuple[WorkflowResult, list[str]]:
    from mollog import get_logger

    logger = get_logger("molab.workflow.execute")
    handler = _Collect()
    logger.add_handler(handler)
    try:
        value = fn()
    finally:
        logger.remove_handler(handler)
    return value, handler.messages


def _drop_config_hash(run: Run, execution_id: str) -> None:
    path = run.execution_dir(execution_id) / "execution.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(type(loaded).__name__)
    environment = loaded.get("environment")
    if not isinstance(environment, dict):
        raise TypeError(type(environment).__name__)
    del environment["config_hash"]
    path.write_text(json.dumps(loaded), encoding="utf-8")


class TestExecuteRun:
    def test_one_step_execute_returns_per_task_outputs(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        result = run.execute(WorkflowCompiler().compile(_build_wf()))
        assert result.status == "succeeded"
        assert result.outputs["double"] == 6
        assert result.outputs["summarize"] == "got 6"
        assert run.status_summary.by_status == {"succeeded": 1}
        assert [e.status.value for e in run.executions] == ["succeeded"]
        assert len(run.executions) == 1

    def test_task_failure_raises_and_persists_failed_run(self, tmp_path: Path) -> None:
        wf = Workflow(name="boom")

        @wf.task
        def explode(x: int) -> int:
            raise ZeroDivisionError("bad cell")

        run = _make_run(tmp_path)
        with pytest.raises(RunFailedError) as excinfo:
            run.execute(wf)
        assert run.status_summary.by_status == {"failed": 1}
        assert run.is_retryable is True
        assert [e.status.value for e in run.executions] == ["failed"]
        # The exception surfaces WHY and carries the partial WorkflowResult.
        assert "ZeroDivisionError" in str(excinfo.value)
        assert excinfo.value.result.status == "failed"

    def test_task_failure_persists_real_traceback_in_error_txt(self, tmp_path: Path) -> None:
        """The engine swallows the task exception, but its live traceback must
        still reach ``executions/<exec_id>/traceback.txt`` — the documented "with
        traceback" trace file, not a placeholder note."""
        wf = Workflow(name="boom")

        @wf.task
        def explode(x: int) -> int:
            raise ZeroDivisionError("bad cell")

        run = _make_run(tmp_path)
        with pytest.raises(RunFailedError):
            run.execute(wf)

        exec_id = run.executions[-1].id
        error_txt = Path(str(run.run_dir)) / "executions" / exec_id / "traceback.txt"
        assert error_txt.exists()
        content = error_txt.read_text()
        assert "Traceback (most recent call last):" in content
        assert "ZeroDivisionError: bad cell" in content
        # The task-body frame is part of the stack — this is a REAL traceback.
        assert 'raise ZeroDivisionError("bad cell")' in content
        assert "No Python traceback was captured" not in content

    def test_fresh_requires_rerun(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        with pytest.raises(ValueError, match="rerun=True"):
            run.execute(_build_wf(), fresh=True)

    def test_fresh_rerun_records_bypass_cache(self, tmp_path: Path) -> None:
        """``fresh=True`` bypasses the cache, so the attempt's record says so."""
        flag = tmp_path / "healed"

        def build() -> Workflow:
            wf = Workflow(name="healing")

            @wf.task
            def stage_a(x: int) -> int:
                if not Path(str(flag)).exists():
                    raise RuntimeError("not healed yet")
                return x

            return wf

        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            run.execute(build())
        flag.write_text("ok")

        run.execute(build(), rerun=True, fresh=True)

        assert [e.bypass_cache for e in run.executions] == [False, True]
        assert run.executions[-1].mode.value == "rerun"
        # The record is the request's only home — no side-channel marker file.
        assert list(Path(str(run.path)).rglob("fresh.json")) == []

    def test_failed_then_explicit_retry_verbs(self, tmp_path: Path) -> None:
        """Retrying is explicit: a failed run refuses a plain call, and
        ``rerun=True`` opens a fresh Execution."""
        flag = tmp_path / "healed"

        def build() -> Workflow:
            wf = Workflow(name="healing")

            @wf.task
            def stage_a(x: int) -> int:
                return x + 1

            @wf.task(depends_on=["stage_a"])
            def stage_b(stage_a: int) -> int:
                if not Path(str(flag)).exists():
                    raise RuntimeError("not healed yet")
                return stage_a * 100

            return wf

        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            run.execute(build())
        assert run.status_summary.by_status == {"failed": 1}
        assert len(run.executions) == 1

        flag.write_text("ok")
        # A plain call on a retryable run refuses — retrying is an explicit verb.
        with pytest.raises(RunNotExecutableError, match="rerun=True"):
            run.execute(build())
        result = run.execute(build(), rerun=True)
        assert result.status == "succeeded"
        assert result.outputs["stage_b"] == 200
        # A retry opens a NEW execution (v2 never reopens an attempt).
        assert len(run.executions) == 2
        assert [e.mode.value for e in run.executions] == ["initial", "rerun"]

    def test_resume_with_checkpoint_creates_resume_execution(self, tmp_path: Path) -> None:
        """A checkpoint is an optional resume input; with one, resume opens e02."""
        run = _make_run(tmp_path)
        with run.start() as ctx:
            cp = ctx.checkpoint("epoch1", data={"step": 1})
            ctx.mark_failed("boom")
        assert [e.status.value for e in run.executions] == ["failed"]

        result = run.execute(_build_wf(), resume=True, checkpoint=cp.id)

        assert result.status == "succeeded"
        assert result.outputs == {"double": 6, "summarize": "got 6"}
        assert [e.mode.value for e in run.executions] == ["initial", "resume"]
        resumed = run.executions[1]
        assert resumed.id == "e02"
        assert resumed.based_on_execution_id == "e01"
        assert resumed.checkpoint_artifact_id == cp.id

    def test_rerun_after_success_opens_rerun(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        run.execute(_build_wf())

        result = run.execute(_build_wf(), rerun=True)

        assert result.status == "succeeded"
        assert [e.mode.value for e in run.executions] == ["initial", "rerun"]
        assert run.executions[1].based_on_execution_id == "e01"

    def test_resume_without_checkpoint_seeds_from_predecessor(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"

        def build() -> Workflow:
            wf = Workflow(name="healing")

            @wf.task
            def stage_a(x: int) -> int:
                return x + 1

            @wf.task(depends_on=["stage_a"])
            def stage_b(stage_a: int) -> int:
                if not Path(str(flag)).exists():
                    raise RuntimeError("not healed yet")
                return stage_a * 100

            return wf

        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            run.execute(build())
        # e01 recorded stage_a == 2; the sentinel 41 can only reach stage_b
        # through a seed taken from e01's journal (a recompute yields 2).
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        flag.write_text("ok")

        result = run.execute(build(), resume=True)

        assert result.status == "succeeded"
        assert [e.mode.value for e in run.executions] == ["initial", "resume"]
        assert run.executions[1].based_on_execution_id == "e01"
        assert result.outputs["stage_b"] == 4100

    def test_running_run_raises(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        ctx = run.start()
        ctx.__enter__()
        try:
            with pytest.raises(RunNotExecutableError, match="cancel"):
                run.execute(_build_wf(), rerun=True)
        finally:
            ctx.__exit__(None, None, None)

    def test_sync_facade_inside_event_loop_raises(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)

        async def inner() -> None:
            run.execute(_build_wf())

        with pytest.raises(RuntimeError, match="aexecute"):
            asyncio.run(inner())

    def test_async_variant(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        result = asyncio.run(run.aexecute(_build_wf()))
        assert result.status == "succeeded"
        assert result.outputs["summarize"] == "got 6"

    def test_resume_after_success_refuses(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        run.execute(_build_wf())

        with pytest.raises(RunNotExecutableError):
            run.execute(_build_wf(), resume=True)

        assert len(run.executions) == 1

    def test_records_workflow_digest_at_start(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        compiled = WorkflowCompiler().compile(_build_wf())

        run.execute(compiled)

        digest = run.executions[0].workflow_digest
        assert digest == compiled.workflow_digest
        assert isinstance(digest, str)
        assert digest.startswith("sha256:")

    def test_starts_precreated_queued_execution(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        created = run._create_execution()
        assert created.id == "e01"
        assert created.status == ExecutionStatus.QUEUED

        result = _execute_run(_build_wf(), run, execution_id="e01")

        assert result.status == "succeeded"
        assert result.outputs == {"double": 6, "summarize": "got 6"}
        assert [item.id for item in run.executions] == ["e01"]
        digest = run.executions[0].workflow_digest
        assert isinstance(digest, str) and digest != ""

    def test_resume_record_seeds_from_based_on_not_latest(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"
        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            _execute_run(_healing_wf(flag), run)
        with pytest.raises(RunFailedError):
            _execute_run(_healing_wf(flag), run, rerun=True)
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        poison_node_output(run.run_dir, "e02", "stage_a", 51)
        flag.write_text("ok", encoding="utf-8")
        created = run._create_execution(mode=ExecutionMode.RESUME, predecessor="e01")
        assert created.id == "e03"

        result = _execute_run(_healing_wf(flag), run, execution_id="e03")

        assert result.outputs["stage_b"] == 4100
        resumed = run.execution("e03")
        assert resumed.mode.value == "resume"
        assert resumed.based_on_execution_id == "e01"

    def test_reproduce_record_bypasses_cache(self, tmp_path: Path) -> None:
        counter = tmp_path / "counter"
        wf = Workflow(name="counting")

        @wf.task
        def count(x: int) -> int:
            previous = counter.read_text(encoding="utf-8") if counter.exists() else ""
            counter.write_text(previous + "1\n", encoding="utf-8")
            return x

        run = _make_run(tmp_path, params={"x": 1})
        _execute_run(wf, run)
        assert counter.read_text(encoding="utf-8") == "1\n"
        _execute_run(wf, run, rerun=True)
        assert counter.read_text(encoding="utf-8") == "1\n"
        record = run._create_execution(mode=ExecutionMode.REPRODUCE)
        assert record.id == "e03"
        assert record.bypass_cache is True

        _execute_run(wf, run, execution_id="e03")

        assert counter.read_text(encoding="utf-8") == "1\n1\n"
        reproduced = run.execution("e03")
        assert reproduced.mode.value == "reproduce"
        assert reproduced.based_on_execution_id == "e02"

    def test_resume_with_different_profile_drops_all_seeds(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"
        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            _execute_run(
                _healing_wf(flag),
                run,
                profile_config=ProfileConfig({"k": 1}, name="cpu"),
            )
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        flag.write_text("ok", encoding="utf-8")

        def _resume() -> WorkflowResult:
            return _execute_run(
                _healing_wf(flag),
                run,
                resume=True,
                profile_config=ProfileConfig({"k": 2}, name="cpu"),
            )

        result, messages = _capture_execute_logs(_resume)

        assert result.outputs["stage_b"] == 200
        resumed = run.execution("e02")
        assert resumed.mode.value == "resume"
        assert resumed.based_on_execution_id == "e01"
        assert (
            resumed.environment["config_hash"] == ProfileConfig({"k": 2}, name="cpu").content_hash()
        )
        assert len(messages) == 1
        assert "config_hash" in messages[0]
        assert "e01" in messages[0]

    def test_resume_with_same_profile_keeps_seeds(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"
        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            _execute_run(
                _healing_wf(flag),
                run,
                profile_config=ProfileConfig({"k": 1}, name="cpu"),
            )
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        flag.write_text("ok", encoding="utf-8")

        def _resume() -> WorkflowResult:
            return _execute_run(
                _healing_wf(flag),
                run,
                resume=True,
                profile_config=ProfileConfig({"k": 1}, name="cpu"),
            )

        result, messages = _capture_execute_logs(_resume)

        assert result.outputs["stage_b"] == 4100
        assert [message for message in messages if "config_hash" in message] == []

    def test_resume_drops_seeds_when_config_hash_unrecorded(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"
        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            _execute_run(_healing_wf(flag), run)
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        _drop_config_hash(run, "e01")
        flag.write_text("ok", encoding="utf-8")

        def _resume() -> WorkflowResult:
            return _execute_run(_healing_wf(flag), run, resume=True)

        result, messages = _capture_execute_logs(_resume)

        assert result.outputs["stage_b"] == 200
        assert len(messages) == 1

    def test_resume_via_seam_inherits_profile_and_keeps_seeds(self, tmp_path: Path) -> None:
        flag = tmp_path / "healed"
        run = _make_run(tmp_path, params={"x": 1})
        with pytest.raises(RunFailedError):
            _execute_run(
                _healing_wf(flag),
                run,
                profile_config=ProfileConfig({"k": 1}, name="cpu"),
            )
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        flag.write_text("ok", encoding="utf-8")

        def _resume() -> WorkflowResult:
            result = run.execute(_healing_wf(flag), resume=True)
            if not isinstance(result, WorkflowResult):
                raise TypeError(type(result).__name__)
            return result

        result, messages = _capture_execute_logs(_resume)

        assert result.outputs["stage_b"] == 4100
        assert (
            run.execution("e02").environment["config_hash"]
            == run.execution("e01").environment["config_hash"]
        )
        assert [message for message in messages if "config_hash" in message] == []

    def test_failure_before_enter_cancels_created_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = _make_run(tmp_path)

        def _raise_runtime_error(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("start failed")

        monkeypatch.setattr(run, "start", _raise_runtime_error)
        with pytest.raises(RuntimeError, match="start failed"):
            _execute_run(_build_wf(), run)
        assert [(item.id, item.status.value) for item in run.executions] == [("e01", "cancelled")]

        monkeypatch.undo()
        result = run.execute(_build_wf(), rerun=True)
        assert isinstance(result, WorkflowResult)
        assert result.status == "succeeded"

    def test_execution_id_differing_profile_config_leaves_record_queued(
        self, tmp_path: Path
    ) -> None:
        run = _make_run(tmp_path)
        created = run._create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))
        assert created.id == "e01"
        wf = _build_wf()

        with pytest.raises(ValueError, match="profile_config"):
            _execute_run(
                wf,
                run,
                execution_id="e01",
                profile_config=ProfileConfig({"k": 2}, name="cpu"),
            )

        assert run.execution("e01").status == ExecutionStatus.QUEUED
        result = _execute_run(wf, run, execution_id="e01")
        assert result.status == "succeeded"

    def test_failure_message_names_execution_dir(self, tmp_path: Path) -> None:
        wf = Workflow(name="boom")

        @wf.task
        def explode(x: int) -> int:
            raise ZeroDivisionError("bad cell")

        run = _make_run(tmp_path)
        with pytest.raises(RunFailedError) as excinfo:
            run.execute(wf)

        message = str(excinfo.value)
        assert f"Execution evidence under {run.execution_dir('e01')}" in message
        assert "traceback.txt" not in message

    def test_importing_execute_does_not_rebind_seam(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        script = tmp_path / "seam.py"
        script.write_text(
            "\n".join(
                [
                    "import molab",
                    "from molab.workspace.run import require_run_executor",
                    "a = require_run_executor()",
                    "import molab.workflow.execute",
                    "assert require_run_executor() is a",
                    "from molab.workflow import Workflow",
                    "wf = Workflow(name='pipeline')",
                    "",
                    "@wf.task",
                    "def double(x: int) -> int:",
                    "    return x * 2",
                    "",
                    f"ws = molab.Workspace({str(workspace)!r}, name='lab')",
                    "run = ws.add_project('demo').add_experiment('pipeline').add_run(",
                    "    params={'x': 3}",
                    ")",
                    "result = run.execute(wf)",
                    "assert result.status == 'succeeded'",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, str(script)],
            check=False,
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 0, completed.stderr

    def test_execution_id_rejects_creation_args(self, tmp_path: Path) -> None:
        from molab.workflow.execute import execute_run

        run = _make_run(tmp_path)
        created = run._create_execution()
        assert created.id == "e01"
        assert created.status == ExecutionStatus.QUEUED
        wf = _build_wf()

        with pytest.raises(ValueError):
            _execute_run(wf, run, execution_id="e01", resume=True)
        with pytest.raises(ValueError):
            _execute_run(wf, run, execution_id="e01", rerun=True)
        with pytest.raises(ValueError):
            _execute_run(wf, run, execution_id="e01", fresh=True)
        with pytest.raises(ValueError):
            execute_run(wf, run, execution_id="e01", checkpoint_artifact_id="x")

        assert [item.id for item in run.executions] == ["e01"]
        assert run.execution("e01").status == ExecutionStatus.QUEUED

    def test_execution_id_must_be_queued(self, tmp_path: Path) -> None:
        run = _make_run(tmp_path)
        wf = _build_wf()
        succeeded = _execute_run(wf, run)
        assert succeeded.status == "succeeded"

        with pytest.raises(RunNotExecutableError, match="queued"):
            _execute_run(wf, run, execution_id="e01")
        with pytest.raises(RunNotExecutableError):
            _execute_run(wf, run, execution_id="e09")

        assert len(run.executions) == 1

    def test_checkpoint_without_resume_is_value_error(self, tmp_path: Path) -> None:
        wf = Workflow(name="boom")

        @wf.task
        def explode(x: int) -> int:
            raise ZeroDivisionError("bad cell")

        run = _make_run(tmp_path)
        with pytest.raises(RunFailedError):
            run.execute(wf)
        assert len(run.executions) == 1

        # Run.execute's frozen kwarg is ``checkpoint`` (run.py), not the record field name.
        with pytest.raises(ValueError):
            run.execute(_build_wf(), rerun=True, checkpoint="x")

        assert len(run.executions) == 1


class TestWorkspaceRunExecutor:
    def test_read_outputs_matches_the_public_reader(self, tmp_path: Path) -> None:
        from molab.workflow import read_outputs
        from molab.workspace.run import require_run_executor

        run = _make_run(tmp_path)
        run.execute(_build_wf())

        outputs = require_run_executor().read_outputs(run, "e01")

        assert outputs == read_outputs(run, "e01")
        assert outputs == {"double": 6, "summarize": "got 6"}

    def test_factory_returns_seam_implementation(self, tmp_path: Path) -> None:
        import molab.workflow
        import molab.workflow.execute
        from molab.workflow.execute import workspace_run_executor

        first, second = workspace_run_executor(), workspace_run_executor()
        assert first is not second
        for member in ("execute", "aexecute", "read_outputs"):
            assert callable(getattr(first, member)), member
        assert "workspace_run_executor" in molab.workflow.execute.__all__
        assert "workspace_run_executor" not in molab.workflow.__all__

        wf = Workflow(name="single")

        @wf.task
        def train() -> dict:
            return {"loss": 0.125}

        run = _make_run(tmp_path)
        run.execute(WorkflowCompiler().compile(wf))
        assert workspace_run_executor().read_outputs(run, "e01") == {"train": {"loss": 0.125}}

    def test_document_without_memo_runs_constant_add(self, tmp_path: Path) -> None:
        from molab.workflow.execute import workspace_run_executor

        default_binding_registry.clear()
        ws = Workspace(tmp_path / "ws", name="ws")
        exp = ws.add_project("p").add_experiment("calc")
        exp.bind_workflow("document", document=_CONSTANT_ADD)
        run = exp.add_run(params={"seed": 1})

        workspace_run_executor().execute(run, None)

        latest = run.executions[-1]
        assert latest.status.value == "succeeded"
        assert workspace_run_executor().read_outputs(run, latest.id)["c"] == 5.0

    def test_unbound_experiment_names_the_missing_binding(self, tmp_path: Path) -> None:
        from molab.workflow.execute import workspace_run_executor

        default_binding_registry.clear()
        ws = Workspace(tmp_path / "ws", name="ws")
        run = ws.add_project("p").add_experiment("bare").add_run(params={"seed": 1})

        with pytest.raises(WorkflowRecoveryError, match=r"^no workflow bound"):
            workspace_run_executor().execute(run, None)

    def test_explicit_workflow_wins_over_the_document(self, tmp_path: Path) -> None:
        from molab.workflow.execute import workspace_run_executor

        default_binding_registry.clear()
        ws = Workspace(tmp_path / "ws", name="ws")
        exp = ws.add_project("p").add_experiment("calc")
        exp.bind_workflow("document", document=_CONSTANT_ADD)
        run = exp.add_run(params={"seed": 1})
        workflow = Workflow(name="only-w")

        @workflow.task
        def lone() -> int:
            return 7

        workspace_run_executor().execute(run, WorkflowCompiler().compile(workflow))

        latest = run.executions[-1]
        assert latest.status.value == "succeeded"
        assert workspace_run_executor().read_outputs(run, latest.id) == {"lone": 7}


class TestVerbMessages:
    def test_resume_and_rerun_together_create_a_new_execution(self) -> None:
        from molab.workflow.execute import _check_verbs

        with pytest.raises(ValueError, match="new Execution") as caught:
            _check_verbs(
                resume=True,
                rerun=True,
                fresh=False,
                checkpoint=None,
                execution_id=None,
            )

        assert "reopen" not in str(caught.value)
