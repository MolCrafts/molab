"""``WorkflowRuntime.execute`` — the runtime API contract.

Post-rectification the runtime takes an opaque duck-typed ``run_context`` and a
``Mapping[str, Any]`` config — never a ``Workspace.Run`` or ``ProfileConfig``
(the legacy ``run=`` kwarg is gone; ``run_dir=`` accepts a path directly). This
file owns that boundary: failure→status, run_context handling (duck-typed, never
exposed on the public ``TaskContext``), executions materialization, the bare
``Runnable`` protocol body, the ``scratch_root``/``ctx.workdir`` contract, and
the execution-id ownership rule (the workspace allocates ``eNN``; the runtime
only reads one from the caller or the run context, refuses to persist without
one, and reports ``None`` for a bare in-memory run).

Graph topology (chains, diamonds, dict-merge binding, explicit parallelism) is
owned by ``test_parallel`` / ``test_by_name_binding`` / ``test_values_on_edges``
/ ``test_sync_tasks`` — not re-asserted here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from molab.workflow import TaskContext, Workflow, WorkflowCompiler, WorkflowRuntime


class _RunContextStub:
    """Minimal duck-typed ``run_context`` — what the runtime now requires.

    Exposes ``.run_dir`` / ``.config`` / ``.run`` so the runtime can extract a
    run dir and forward the value to its private channel, plus ``.execution_id``
    — the workspace-allocated attempt id the runtime reads (it never mints one).
    Pass ``execution_id=None`` for a context that carries no id. No
    ``Workspace`` import.
    """

    def __init__(
        self,
        *,
        run_dir: Path,
        config: dict | None = None,
        run_id: str | None = None,
        params: dict | None = None,
        execution_id: str | None = "e01",
    ):
        self.run_dir = run_dir
        self.execution_id = execution_id
        self.bypass_cache = False
        self.config = config or {}
        # Root-task params reach the body by name (engine reads run_context.params).
        self.params = params or {}
        self.run = type(
            "RunStub",
            (),
            {"id": run_id or "stub-run", "run_dir": run_dir},
        )()


def _ok_workflow():
    """A one-task workflow that always succeeds."""
    wf = Workflow(name="ok")

    @wf.task
    async def step(ctx: TaskContext) -> str:
        return "ok"

    return WorkflowCompiler().compile(wf)


@pytest.mark.asyncio
class TestWorkflowRuntimeExecute:
    async def test_task_failure_propagates_to_failed_status(self):
        wf = Workflow(name="fail")

        @wf.task
        async def boom(ctx):
            raise RuntimeError("oops")

        result = await WorkflowRuntime().execute(WorkflowCompiler().compile(wf))
        assert result.status == "failed"

    async def test_external_runnable_protocol_body_executes(self):
        # A bare duck-typed body (no ``Task`` base — the ``Runnable`` protocol
        # surface) added via ``.add`` executes and its return becomes the output.
        class External:
            async def execute(self, ctx) -> int:
                return 99

        spec = WorkflowCompiler().compile(Workflow(name="ext").add(External(), name="ext"))
        result = await WorkflowRuntime().execute(spec)
        assert result.outputs["ext"] == 99

    async def test_run_context_is_not_exposed_on_task_ctx(self, tmp_path):
        # Pure-task-context contract: run_context is NOT forwarded to the public
        # TaskContext. A task accessing ctx.run_context raises AttributeError; the
        # engine still drives the run via its private channel.
        wf = Workflow(name="no-run-context")

        run_ctx = _RunContextStub(
            run_dir=tmp_path / "run",
            config={"epochs": 1, "dataset": "md17"},
        )

        @wf.task
        async def inspect(ctx: TaskContext) -> bool:
            assert not hasattr(ctx, "run_context")
            return True

        result = await WorkflowRuntime().execute(
            WorkflowCompiler().compile(wf), run_context=run_ctx
        )
        assert result.status == "succeeded"
        assert result.outputs["inspect"] is True

    async def test_duck_typed_run_context_needs_no_workspace_and_writes_executions(self, tmp_path):
        """The runtime drives a workflow with a stub run_context that has no
        Workspace ancestry whatsoever, and materializes workflow.json under
        run_dir/executions/<the context's execution_id>/."""
        wf = Workflow(name="duck")

        run_ctx = _RunContextStub(run_dir=tmp_path / "stub-run", execution_id="e01")

        @wf.task
        async def step(ctx: TaskContext) -> str:
            return "ok"

        result = await WorkflowRuntime().execute(
            WorkflowCompiler().compile(wf), run_context=run_ctx
        )
        assert result.status == "succeeded"
        assert result.outputs["step"] == "ok"
        assert result.execution_id == "e01"
        assert (run_ctx.run_dir / "executions" / "e01" / "workflow.json").is_file()

    async def test_run_context_public_id_names_the_execution(self, tmp_path: Path) -> None:
        """The runtime reads the active attempt from the context's public
        ``id`` — the surface a real ``ExecutionContext`` exposes — and
        persists under ``executions/<id>/``, with no private-attribute probe."""

        class _PublicIdContext:
            def __init__(self, run_dir: Path) -> None:
                self.id = "e01"
                self.run_dir = run_dir
                self.bypass_cache = False

        run_ctx = _PublicIdContext(tmp_path / "run")
        result = await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx)
        assert result.status == "succeeded"
        assert result.execution_id == "e01"
        assert (run_ctx.run_dir / "executions" / "e01" / "workflow.json").is_file()

    async def test_run_dir_without_execution_id_raises(self, tmp_path: Path) -> None:
        """Persisting under a ``run_dir`` needs a workspace-allocated id: the
        runtime refuses to invent one and writes nothing."""
        run_dir = tmp_path / "r"
        with pytest.raises(ValueError, match="execution_id"):
            await WorkflowRuntime().execute(_ok_workflow(), run_dir=run_dir)
        assert (run_dir / "executions").exists() is False

    async def test_run_context_without_execution_id_raises(self, tmp_path: Path) -> None:
        """A run context that carries a run dir but no execution id is refused
        the same way as a bare ``run_dir``."""
        run_ctx = _RunContextStub(run_dir=tmp_path / "r", execution_id=None)
        with pytest.raises(ValueError, match="execution_id"):
            await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx)
        assert (run_ctx.run_dir / "executions").exists() is False

    async def test_persist_false_needs_no_execution_id(self, tmp_path: Path) -> None:
        """``persist=False`` (SubWorkflow inner runs) writes no journal, so a run
        context without an id is fine and no ``workflow.json`` appears."""
        run_ctx = _RunContextStub(run_dir=tmp_path / "r", execution_id=None)
        result = await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx, persist=False)
        assert result.status == "succeeded"
        assert list(run_ctx.run_dir.rglob("workflow.json")) == []

    async def test_bare_execute_has_no_execution_id(self) -> None:
        """A bare in-memory run is not an Execution: its id is ``None``."""
        result = await WorkflowRuntime().execute(_ok_workflow())
        assert result.status == "succeeded"
        assert result.execution_id is None

    async def test_runtime_exposes_no_id_minter_or_fresh_marker(self) -> None:
        """The runtime neither mints execution ids nor writes fresh markers."""
        assert hasattr(WorkflowRuntime, "make_execution_id") is False
        assert hasattr(WorkflowRuntime, "request_fresh_execution") is False

    async def test_scratch_root_gives_every_task_a_workdir(self, tmp_path: Path) -> None:
        """``scratch_root=`` closes the ctx.workdir contract for bare executions.

        A plan-materialized driver runs ``WorkflowRuntime().execute(compiled,
        config=...)`` with NO tracked Run, but task bodies use ``ctx.workdir`` for
        scratch files. ``scratch_root`` mounts the content-addressed materialization
        store at an explicit location so ``ctx.workdir`` is never ``None``.
        """
        wf = Workflow(name="scratch-demo")

        @wf.task
        async def write_report(ctx: TaskContext) -> dict:
            assert ctx.workdir is not None
            path = ctx.workdir / "report.json"
            path.write_text("{}")
            return {"report": str(path)}

        scratch = tmp_path / "scratch"
        result = await WorkflowRuntime().execute(
            WorkflowCompiler().compile(wf), scratch_root=scratch
        )
        assert result.status == "succeeded"
        report = Path(result.outputs["write_report"]["report"])
        assert report.exists()
        assert scratch in report.parents

    async def test_without_scratch_root_keeps_workdir_none(self, tmp_path: Path) -> None:
        """No silent default: a bare execution that mounts no scratch_root keeps
        ``ctx.workdir`` as ``None`` (embedders must opt in explicitly — a cwd
        default would litter every caller's working directory)."""
        wf = Workflow(name="no-scratch")

        @wf.task
        async def probe(ctx: TaskContext) -> dict:
            return {"workdir": ctx.workdir}

        result = await WorkflowRuntime().execute(WorkflowCompiler().compile(wf))
        assert result.status == "succeeded"
        assert result.outputs["probe"]["workdir"] is None


@pytest.mark.asyncio
class TestWorkflowRuntimeStart:
    async def test_run_dir_without_execution_id_raises_before_scheduling(
        self, tmp_path: Path
    ) -> None:
        """``start`` refuses a ``run_dir`` without an id synchronously — no
        background task is scheduled and nothing is written."""
        run_dir = tmp_path / "r"
        before = asyncio.all_tasks()
        with pytest.raises(ValueError, match="execution_id"):
            await WorkflowRuntime().start(_ok_workflow(), run_dir=run_dir)
        assert asyncio.all_tasks() - before == set()
        assert (run_dir / "executions").exists() is False

    async def test_bare_start_handle_has_no_execution_id(self) -> None:
        """A bare background run reports ``execution_id is None`` and completes."""
        handle = await WorkflowRuntime().start(_ok_workflow())
        assert handle.execution_id is None
        assert (await handle.wait()).status == "succeeded"
