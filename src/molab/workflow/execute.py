"""One-step tracked execution — run a workflow against a workspace ``Run``.

``execute_run(workflow, run)`` folds the driver dance (``run.start()`` context
+ ``WorkflowRuntime().execute(..., run_context=ctx)`` + asyncio plumbing) into
a single call on the **same execution path as** ``molab run``: the
``RunContext`` lifecycle owns the status machine, ``run.json`` hot state
and the ``alive``-file ownership heartbeat; the workflow engine owns
scheduling, caching and node-level persistence. Nothing here is a second
path — it is the CLI's in-process handler, made importable.

Verb selection follows the canonical run-status law (see CLAUDE.md); the
three keywords mirror the CLI exactly — ``resume`` is ``--resume`` (reopen
the last execution, seed completed nodes), ``rerun`` is ``--rerun`` (fresh
attempt, no seeding) and ``fresh`` is ``--fresh`` (bypass the
content-addressed cache read; only meaningful with ``rerun=True``). Retrying
is always explicit — with neither flag, a retryable run refuses instead of
silently resuming:

======================  ====================  ==================  ==================
run status              no flag               ``resume=True``     ``rerun=True``
======================  ====================  ==================  ==================
``pending``             run (first attempt)   *error* — run's job  *error* — run's job
``failed``/``cancelled``  :class:`RunNotExecutableError`  resume (reopen +    rerun (new
                        — retrying is explicit  seed completed)     ``exec-<id>-N``)
``succeeded``           :class:`RunNotExecutableError` — done is done
``running``             :class:`RunNotExecutableError` — cancel it first
======================  ====================  ==================  ==================

A task failure raises :class:`RunFailedError` (carrying the partial
``WorkflowResult``) *after* the failed state has been persisted — loud like
the CLI's non-zero exit, never a silently-failed return value.

This module also registers the workspace ``set_run_executor`` inversion seam
at import time, which is what makes ``Run.execute`` / ``Run.aexecute`` and
``RunSet.execute`` work without the workspace layer ever importing workflow.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.run import set_run_executor

from ._engine.persistence import seed_from_execution
from ._engine.runtime import WorkflowRuntime
from .compiled import CompiledWorkflow
from .compiler import Workflow, WorkflowCompiler

if TYPE_CHECKING:
    from molab.profile import ProfileConfig
    from molab.workspace.run import Run

    from .types import WorkflowResult

__all__ = [
    "RunFailedError",
    "RunNotExecutableError",
    "aexecute_run",
    "execute_run",
]


class RunNotExecutableError(RuntimeError):
    """The run's current status is outside ``execute_run``'s verb domain."""


class RunFailedError(RuntimeError):
    """A task failed during ``execute_run``; the run is persisted as failed.

    Carries the partial :class:`~molab.workflow.WorkflowResult` on
    ``.result`` (completed upstream outputs remain readable), so callers that
    aggregate failures — e.g. ``RunSet.execute`` — keep the honest summary.
    """

    def __init__(self, message: str, *, result: WorkflowResult) -> None:
        super().__init__(message)
        self.result = result


def _ensure_compiled(workflow: object) -> CompiledWorkflow:
    """Normalize *workflow* to a :class:`CompiledWorkflow` (auto-compile)."""
    if isinstance(workflow, CompiledWorkflow):
        return workflow
    if isinstance(workflow, Workflow):
        return WorkflowCompiler().compile(workflow)
    raise TypeError(
        f"execute_run expects a CompiledWorkflow or a Workflow, got {type(workflow).__name__}"
    )


def _select_verb(
    run: Run,
    *,
    resume: bool,
    rerun: bool,
    checkpoint_artifact_id: str | None,
) -> tuple[ExecutionMode, str | None, dict | None]:
    """Select a new Execution; an existing attempt is never reopened."""
    executions = run.executions
    if not executions:
        if resume or rerun:
            raise RunNotExecutableError(
                f"run {run.id} has no prior Execution; start it without a retry verb"
            )
        return ExecutionMode.INITIAL, None, None
    if not (resume or rerun):
        raise RunNotExecutableError(
            f"run {run.id} already has {len(executions)} Execution(s); choose rerun=True "
            "or resume=True explicitly"
        )
    predecessor = executions[-1]
    if predecessor.status in {
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
        ExecutionStatus.FINALIZING,
    }:
        raise RunNotExecutableError(
            f"latest Execution {predecessor.id} is still {predecessor.status.value}; "
            "cancel it first, or select a terminal predecessor explicitly before retrying"
        )
    if predecessor.status is ExecutionStatus.SUCCEEDED:
        raise RunNotExecutableError(
            f"run {run.id} is succeeded — done is done; start a new Run instead of retrying"
        )
    if rerun:
        return ExecutionMode.RERUN, predecessor.id, None
    if checkpoint_artifact_id is None:
        raise RunNotExecutableError(
            "resume requires checkpoint_artifact_id; a workflow snapshot alone is "
            "execution evidence, not a resumable data Artifact"
        )
    _prior_id, seeds = seed_from_execution(run)
    return ExecutionMode.RESUME, predecessor.id, seeds


def _raise_if_failed(run: Run, result: WorkflowResult) -> WorkflowResult:
    if result.status == "succeeded":
        return result
    execution = next(
        (item for item in run.executions if item.id == getattr(result, "execution_id", None)),
        None,
    )
    error = execution.error if execution is not None else None
    detail = str(error.get("message")) if error is not None else "see Execution evidence"
    exec_id = getattr(result, "execution_id", None)
    error_txt = (
        f"{run.run_dir}/executions/{exec_id}/traceback.txt"
        if exec_id
        else f"{run.run_dir}/executions/<exec_id>/traceback.txt"
    )
    raise RunFailedError(
        f"run {run.id} failed — {detail} "
        f"(details: {error_txt}; retry with resume=True to continue from the "
        f"failed node, or rerun=True to re-execute from the top)",
        result=result,
    )


async def aexecute_run(
    workflow: object,
    run: Run,
    *,
    resume: bool = False,
    rerun: bool = False,
    fresh: bool = False,
    profile_config: ProfileConfig | None = None,
    checkpoint_artifact_id: str | None = None,
) -> WorkflowResult:
    """Async one-step tracked execution. See :func:`execute_run`."""
    if resume and rerun:
        raise ValueError(
            "resume=True and rerun=True are mutually exclusive verbs — resume "
            "reopens the last execution, rerun opens a fresh attempt."
        )
    if fresh and not rerun:
        raise ValueError(
            "fresh=True bypasses the cache for an explicit re-execution and "
            "requires rerun=True (mirroring `molab run --rerun --fresh`)."
        )
    compiled = _ensure_compiled(workflow)
    mode, predecessor_id, seed_outputs = _select_verb(
        run,
        resume=resume,
        rerun=rerun,
        checkpoint_artifact_id=checkpoint_artifact_id,
    )
    if seed_outputs and predecessor_id is not None:
        from ._engine.persistence import filter_resume_seeds

        seed_outputs = filter_resume_seeds(
            run.run_dir, predecessor_id, seed_outputs, compiled.snapshots
        )
    with run.start(
        profile_config,
        mode=mode,
        based_on_execution_id=predecessor_id,
        checkpoint_artifact_id=checkpoint_artifact_id,
    ) as ctx:
        result = await WorkflowRuntime().execute(
            compiled,
            run_context=ctx,
            seed_outputs=seed_outputs,
            bypass_cache=fresh,
        )
    return _raise_if_failed(run, result)


def execute_run(
    workflow: object,
    run: Run,
    *,
    resume: bool = False,
    rerun: bool = False,
    fresh: bool = False,
    profile_config: ProfileConfig | None = None,
    checkpoint_artifact_id: str | None = None,
) -> WorkflowResult:
    """Execute *workflow* against *run* in one step and return the result.

    The synchronous facade over :func:`aexecute_run` — owns the event loop via
    ``asyncio.run``. Args:

        workflow: A ``CompiledWorkflow``, or an uncompiled
            ``Workflow`` (compiled automatically).
        run: The workspace :class:`~molab.workspace.run.Run` to execute
            against (status machine / ``ops`` sidecar / heartbeat are driven
            by its ``RunContext`` lifecycle, exactly as under ``molab run``).
        resume: ``True`` reopens a failed/cancelled run's last execution and
            seeds its completed nodes (recompute only the rest) — the CLI's
            ``--resume``. Mutually exclusive with ``rerun``.
        rerun: ``True`` opens a fresh attempt (new ``exec-<run_id>-N``, no
            seeding) for a failed/cancelled run — the CLI's ``--rerun``.
            With neither flag, a retryable run refuses loudly (retrying is
            an explicit verb, never implicit).
        fresh: ``True`` additionally bypasses the content-addressed cache
            *read* for that attempt (results are still written back). Requires
            ``rerun=True`` — the CLI's ``--rerun --fresh``.
        profile_config: Optional molcfg profile applied to the run.

    Returns:
        The ``WorkflowResult`` — ``result.outputs`` maps task name → output.

    Raises:
        RunFailedError: A task failed (state persisted first).
        RunNotExecutableError: Status outside the verb domain (see module doc).
        RuntimeError: Called from inside a running event loop — await
            :func:`aexecute_run` there instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "execute_run() was called from inside a running event loop; "
            "await aexecute_run(...) (or run.aexecute(...)) instead."
        )
    return asyncio.run(
        aexecute_run(
            workflow,
            run,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            profile_config=profile_config,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )
    )


# ── Workspace inversion seam ─────────────────────────────────────────────────


class _WorkspaceRunExecutor:
    """Implements ``molab.workspace.run.RunWorkflowExecutor``.

    ``workflow=None`` resolves the experiment's bound workflow from
    :data:`~molab.workflow.binding.default_binding_registry` (the store
    ``Experiment.run`` / ``Experiment.sweep`` populate) — and fails fast when
    nothing is bound, never falling back.
    """

    @staticmethod
    def _resolve(run: Run, workflow: object | None) -> object:
        if workflow is not None:
            return workflow
        from .binding import default_binding_registry

        bound = default_binding_registry.for_experiment(run.experiment)
        if bound is None:
            raise RuntimeError(
                f"run {run.id}: no workflow bound to experiment "
                f"{run.experiment.id!r} — pass workflow=... or declare it via "
                f"experiment.sweep(workflow, params=...) / experiment.run(workflow, ...)."
            )
        return bound

    def execute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint_artifact_id: str | None = None,
    ) -> object:
        return execute_run(
            self._resolve(run, workflow),
            run,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )

    async def aexecute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint_artifact_id: str | None = None,
    ) -> object:
        return await aexecute_run(
            self._resolve(run, workflow),
            run,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )


# Wire the seam at import time so ``run.execute(workflow)`` works as soon as
# the workflow layer is loaded (the caller necessarily imported it to build
# ``workflow``), without workspace ever importing this layer.
set_run_executor(_WorkspaceRunExecutor())
