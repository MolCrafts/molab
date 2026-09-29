"""``WorkflowRuntime.execute`` — the runtime API contract.

Post-rectification the runtime takes an opaque duck-typed ``run_context`` and a
``Mapping[str, Any]`` config — never a ``Workspace.Run`` or ``ProfileConfig``
(the legacy ``run=`` kwarg is gone; ``run_dir=`` accepts a path directly). This
file owns that boundary: failure→status, run_context handling (duck-typed, never
exposed on the public ``TaskContext``), executions materialization, the bare
``Runnable`` protocol body, the ``scratch_root``/``ctx.workdir`` contract, and
the context contract (the run context names the attempt through ``id`` /
``execution_dir`` / ``based_on_execution_id``; the journal lands in
``execution_dir`` and nowhere else; an incomplete context is a ``TypeError``;
``run_dir=`` / ``execution_id=`` without a context, or a mismatched id, is a
``ValueError``; a bare in-memory run reports ``None`` and writes no journal).

Graph topology (chains, diamonds, dict-merge binding, explicit parallelism) is
owned by ``test_parallel`` / ``test_by_name_binding`` / ``test_values_on_edges``
/ ``test_sync_tasks`` — not re-asserted here.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from molab.workflow import TaskContext, Workflow, WorkflowCompiler, WorkflowRuntime, read_journal
from molab.workspace import Workspace


class _RunContextStub:
    """Minimal duck-typed ``run_context`` — what the runtime requires.

    Names its attempt through ``id`` / ``execution_dir`` /
    ``based_on_execution_id`` (the runtime composes no path: the journal goes
    to ``execution_dir``), plus ``.run_dir`` / ``.config`` / ``.run`` /
    ``.params`` / ``.bypass_cache``. No ``Workspace`` import.
    """

    def __init__(
        self,
        *,
        run_dir: Path,
        execution_dir: Path | None = None,
        config: dict | None = None,
        run_id: str | None = None,
        params: dict | None = None,
        execution_id: str = "e01",
    ):
        self.run_dir = run_dir
        self.id = execution_id
        self.execution_dir = execution_dir or run_dir / "slot" / execution_id
        self.based_on_execution_id = None
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

    async def test_journal_lands_at_the_context_execution_dir(self, tmp_path: Path) -> None:
        """The runtime writes the journal only where the context points — it
        builds no ``executions/<id>`` path under ``run_dir`` itself."""
        run_dir = tmp_path / "stub-run"
        slot = tmp_path / "any" / "slot"
        run_ctx = _RunContextStub(run_dir=run_dir, execution_dir=slot)

        result = await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx)

        assert result.status == "succeeded"
        assert result.execution_id == "e01"
        assert (slot / "workflow.json").is_file()
        assert not (run_dir / "executions").exists()

    async def test_legacy_run_dir_and_context_shape(self, tmp_path: Path) -> None:
        """``run_dir=`` beside a context is accepted but does not locate the
        journal: it lands at ``run.execution_dir(ctx.id)``."""
        ws = Workspace(tmp_path / "ws", name="lab")
        run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
        with run.start() as ctx:
            result = await WorkflowRuntime().execute(
                _ok_workflow(), run_dir=run.run_dir, run_context=ctx, execution_id=ctx.id
            )
        assert result.status == "succeeded"
        assert (run.execution_dir(ctx.id) / "workflow.json").is_file()
        assert read_journal(run, ctx.id)["execution_id"] == ctx.id
        assert len(list(Path(run.run_dir).rglob("workflow.json"))) == 1

    async def test_context_without_execution_dir_raises_type_error(self, tmp_path: Path) -> None:
        """A context that does not name its attempt's directory is refused."""

        class _NoDirContext:
            def __init__(self, run_dir: Path) -> None:
                self.id = "e01"
                self.based_on_execution_id = None
                self.run_dir = run_dir
                self.bypass_cache = False

        run_ctx = _NoDirContext(tmp_path / "run")
        with pytest.raises(TypeError, match="execution_dir"):
            await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx)
        assert list(tmp_path.rglob("workflow.json")) == []

    async def test_run_dir_without_context_raises(self, tmp_path: Path) -> None:
        """A journal belongs to an Execution: ``run_dir=`` alone is refused and
        nothing is written."""
        run_dir = tmp_path / "r"
        with pytest.raises(ValueError, match="run_context"):
            await WorkflowRuntime().execute(_ok_workflow(), run_dir=run_dir)
        assert not run_dir.exists()

    async def test_execution_id_without_context_raises(self) -> None:
        with pytest.raises(ValueError, match="run_context"):
            await WorkflowRuntime().execute(_ok_workflow(), execution_id="e01")

    async def test_mismatched_execution_id_raises(self, tmp_path: Path) -> None:
        """An explicit ``execution_id=`` must be the context's own attempt."""
        run_ctx = _RunContextStub(run_dir=tmp_path / "r")
        with pytest.raises(ValueError, match="e99"):
            await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx, execution_id="e99")
        assert list(tmp_path.rglob("workflow.json")) == []

    async def test_persist_false_writes_no_journal(self, tmp_path: Path) -> None:
        """``persist=False`` (SubWorkflow inner runs) writes no journal."""
        run_ctx = _RunContextStub(run_dir=tmp_path / "r")
        result = await WorkflowRuntime().execute(_ok_workflow(), run_context=run_ctx, persist=False)
        assert result.status == "succeeded"
        assert list(tmp_path.rglob("workflow.json")) == []

    async def test_bare_execute_has_no_execution_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare in-memory run is not an Execution: its id is ``None`` and it
        writes no journal anywhere."""
        monkeypatch.chdir(tmp_path)
        result = await WorkflowRuntime().execute(_ok_workflow())
        assert result.status == "succeeded"
        assert result.execution_id is None
        assert list(tmp_path.rglob("workflow.json")) == []

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
    async def test_run_dir_without_context_raises_before_scheduling(self, tmp_path: Path) -> None:
        """``start`` refuses ``run_dir=`` without a context synchronously — no
        background task is scheduled and nothing is written."""
        run_dir = tmp_path / "r"
        before = asyncio.all_tasks()
        with pytest.raises(ValueError, match="run_context"):
            await WorkflowRuntime().start(_ok_workflow(), run_dir=run_dir)
        assert asyncio.all_tasks() - before == set()
        assert not run_dir.exists()

    async def test_journal_lands_at_the_context_execution_dir(self, tmp_path: Path) -> None:
        slot = tmp_path / "any" / "slot"
        run_ctx = _RunContextStub(run_dir=tmp_path / "r", execution_dir=slot)
        handle = await WorkflowRuntime().start(_ok_workflow(), run_context=run_ctx)
        assert handle.execution_id == "e01"
        assert (await handle.wait()).status == "succeeded"
        doc = json.loads((slot / "workflow.json").read_text())
        assert doc["execution_id"] == "e01"
        assert doc["finished_at"] is not None

    async def test_context_without_execution_dir_raises_type_error(self, tmp_path: Path) -> None:
        run_ctx = SimpleNamespace(id="e01", based_on_execution_id=None, bypass_cache=False)
        with pytest.raises(TypeError, match="execution_dir"):
            await WorkflowRuntime().start(_ok_workflow(), run_context=run_ctx)

    async def test_bare_start_handle_has_no_execution_id(self) -> None:
        """A bare background run reports ``execution_id is None`` and completes."""
        handle = await WorkflowRuntime().start(_ok_workflow())
        assert handle.execution_id is None
        assert (await handle.wait()).status == "succeeded"
