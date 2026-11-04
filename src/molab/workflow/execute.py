"""One-step tracked execution — run a workflow as one attempt.

``execution.execute(workflow)`` starts a queued attempt.
``run.execute(workflow)`` allocates that attempt (first run, resume, or
rerun) and then runs it. Both fold the driver dance (the attempt
context + ``WorkflowRuntime().execute(..., run_context=ctx)`` + asyncio
plumbing) into the same path ``molab run`` uses: the ``RunContext``
lifecycle owns the status machine, the run record and the
``alive``-file ownership heartbeat; the workflow engine owns scheduling,
caching and node-level persistence.

``run.execute`` selects the verb from the latest attempt. With no attempt
and no verb it opens an ``INITIAL`` record. An existing attempt requires
``resume=True`` or ``rerun=True``. ``execution.execute`` starts a ``QUEUED``
record someone else already created. ``resume=True`` opens a new ``RESUME``
attempt and, when its ``config_hash`` matches the predecessor, seeds every
completed node from that predecessor's recorded output refs (pickled values
included); a node that failed re-executes from the same seeded inputs its
record shows. ``rerun=True`` opens a new ``RERUN`` attempt, including after
success; with ``only=("task", ...)`` it is a **partial rerun**: the selection
is recorded on the Execution (``selected_tasks``), exactly those tasks
execute with the inputs their predecessor recorded, every other completed
task is seeded from its record, and every task downstream of a selected one
is journalled ``skipped``. A selected task whose upstream has no usable
recorded output is refused (:class:`RunNotExecutableError` naming it).
``fresh=True`` records ``bypass_cache`` and requires ``rerun=True``. An active
latest attempt must be cancelled first.

``executor=`` (``"thread"`` / ``"process"`` / ``"inline"``) and
``max_workers=`` choose how every task body of the attempt runs; they are
recorded on the Execution (``executor.task_executor`` /
``executor.task_max_workers``) and a pre-created record's values are used
when the call passes none.

Resume and partial rerun share one seeding path,
:func:`molab.workflow.read_attempt_seeds`, and both are driven by the
record alone, so a pre-created QUEUED record (``molab run`` / the server /
a scheduler worker) seeds exactly like an in-process call.

Both doors meet at "start one QUEUED record":

================  =================  =======================  ===========  ============================
latest attempt    no verb            ``resume=True``          ``rerun``    ``execution_id=eNN``
================  =================  =======================  ===========  ============================
none              INITIAL            error                    error        start that QUEUED record
failed/cancelled  error              new RESUME, seed if      new RERUN    start that QUEUED record
/interrupted                         config_hash matches
succeeded         error              error (predecessor rule) new RERUN    start that QUEUED record
queued/running    error (cancel)     error                    error        start that QUEUED record
================  =================  =======================  ===========  ============================

A task failure raises :class:`RunFailedError` (carrying the partial
``WorkflowResult``) *after* the failed state has been persisted — loud like
the CLI's non-zero exit, never a silently-failed return value.

``Run.execute`` / ``Execution.execute`` / ``RunSet.execute`` reach this
module through the workspace inversion seam. The composition root
``molab/__init__`` is the only registrar (a lazy proxy that obtains the
implementation from ``workspace_run_executor()``). Importing this module
does not touch the seam.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from mollog import get_logger

from molab.workspace.domain import Execution, ExecutionMode, ExecutionStatus

from ._engine.executors import check_executor, check_max_workers
from ._engine.persistence import AttemptSeeds, RecordedInputError, read_attempt_seeds
from ._engine.runtime import WorkflowRuntime
from .compiled import CompiledWorkflow
from .compiler import Workflow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from molab._typing import JSONValue
    from molab.profile import ProfileConfig
    from molab.workspace.run import Run, RunWorkflowExecutor

    from .protocols import TaskOutput
    from .types import WorkflowResult

logger = get_logger(__name__)

#: ``Execution.executor`` key recording the run's task executor.
TASK_EXECUTOR_KEY = "task_executor"

#: ``Execution.executor`` key recording the run's worker cap.
TASK_MAX_WORKERS_KEY = "task_max_workers"

__all__ = [
    "TASK_EXECUTOR_KEY",
    "TASK_MAX_WORKERS_KEY",
    "RunFailedError",
    "RunNotExecutableError",
    "aexecute_run",
    "execute_run",
    "workspace_run_executor",
]


class RunNotExecutableError(RuntimeError):
    """The attempt is outside the verb domain of ``run.execute`` / ``execution.execute``."""


class RunFailedError(RuntimeError):
    """A task failed during ``execution.execute``; the attempt is persisted as failed.

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
        return workflow.compile()
    raise TypeError(
        f"execution.execute expects a CompiledWorkflow or a Workflow, got {type(workflow).__name__}"
    )


def _select_mode(run: Run, *, resume: bool, rerun: bool) -> ExecutionMode:
    """Choose the mode of a new Execution. Predecessor rules live in workspace.

    Args:
        run: The run whose latest attempt decides whether a verb is legal.
        resume: Open a ``RESUME`` attempt.
        rerun: Open a ``RERUN`` attempt.

    Returns:
        The mode ``Run._create_execution`` should record.

    Raises:
        RunNotExecutableError: There is no attempt to resume or rerun, an
            attempt already exists and no verb was given, or the latest
            attempt is still active.
    """
    executions = run.executions
    if not executions:
        if resume or rerun:
            raise RunNotExecutableError(
                f"run {run.id} has no prior Execution; start it without a retry verb"
            )
        return ExecutionMode.INITIAL
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
    if resume:
        return ExecutionMode.RESUME
    return ExecutionMode.RERUN


def _create_record(
    run: Run,
    mode: ExecutionMode,
    *,
    checkpoint_artifact_id: str | None,
    fresh: bool,
    profile_config: ProfileConfig | None,
    only: Sequence[str] = (),
    executor: dict[str, JSONValue] | None = None,
) -> Execution:
    """Allocate one QUEUED Execution. Workspace owns the predecessor rules.

    Args:
        run: The run that allocates the attempt id.
        mode: ``INITIAL``, ``RESUME`` or ``RERUN``.
        checkpoint_artifact_id: Optional resume input, stored on the record.
        fresh: Recorded as ``bypass_cache``.
        profile_config: The profile written onto the record at creation.
        only: Recorded as ``selected_tasks`` (a partial rerun).
        executor: Creation-time executor facts (``task_executor`` /
            ``task_max_workers``).

    Returns:
        The new QUEUED record.

    Raises:
        RunNotExecutableError: ``Run.create_execution`` refused the mode.
    """
    try:
        return run.create_execution(
            mode=mode,
            checkpoint_artifact_id=checkpoint_artifact_id,
            bypass_cache=fresh,
            profile_config=profile_config,
            selected_tasks=only,
            executor=executor,
        )
    except ValueError as exc:
        raise RunNotExecutableError(str(exc)) from exc


def _queued_record(run: Run, execution_id: str) -> Execution:
    """Load a pre-created attempt that this call is allowed to start.

    Args:
        run: The run that owns the attempt.
        execution_id: The attempt id (``e01``).

    Returns:
        The QUEUED record.

    Raises:
        RunNotExecutableError: No such attempt, or it is not QUEUED.
    """
    try:
        record = run.execution(execution_id)
    except KeyError:
        raise RunNotExecutableError(f"no Execution {execution_id} on run {run.id}") from None
    if record.status is not ExecutionStatus.QUEUED:
        raise RunNotExecutableError(
            f"Execution {execution_id} is {record.status.value}, not queued"
        )
    return record


def _config_hashes_disagree(record: Execution, prior: Execution) -> bool:
    """True when the two records cannot be shown to share a ``config_hash``."""
    if "config_hash" not in record.environment or "config_hash" not in prior.environment:
        return True
    return record.environment["config_hash"] != prior.environment["config_hash"]


def _attempt_seeds(run: Run, record: Execution, compiled: CompiledWorkflow) -> AttemptSeeds | None:
    """What the attempt *record* takes from its predecessor's records.

    The record decides: a ``RESUME`` seeds every completed node, a ``RERUN``
    with ``selected_tasks`` runs just those (both through
    :func:`read_attempt_seeds`); any other attempt seeds nothing. A missing
    ``config_hash`` on either record, or two different values, drops every
    seed of a RESUME and refuses a partial RERUN (its seeds would mix two
    configs). ``None == None`` matches: neither side named a profile.

    Args:
        run: The run that holds both attempts.
        record: The attempt about to start.
        compiled: The workflow the seeds must still fit.

    Returns:
        The seeds, or ``None`` when there is nothing to take.

    Raises:
        ValueError: The selection names a task the workflow does not have.
        RunNotExecutableError: A partial rerun's config differs from its
            predecessor's, or a selected task needs a recorded value the
            predecessor cannot supply.
    """
    based_on = record.based_on_execution_id
    selection = tuple(record.selected_tasks)
    partial = record.mode is ExecutionMode.RERUN and bool(selection)
    if not based_on or not (record.mode is ExecutionMode.RESUME or partial):
        return None
    prior = run.execution(based_on)
    if _config_hashes_disagree(record, prior):
        ours = record.environment.get("config_hash", "<missing>")
        theirs = prior.environment.get("config_hash", "<missing>")
        if partial:
            raise RunNotExecutableError(
                f"partial rerun {record.id} of {list(selection)}: config_hash {ours!r} "
                f"does not match predecessor {prior.id} config_hash {theirs!r}; its "
                "recorded outputs were computed under another config — rerun with the "
                "predecessor's profile, or rerun the whole workflow"
            )
        logger.warning(
            f"RESUME Execution {record.id} drops every seed: config_hash {ours!r} "
            f"does not match predecessor {prior.id} config_hash {theirs!r}; "
            "不复用任何种子, 全部节点重新计算 (节点缓存照常)"
        )
        return None
    try:
        return read_attempt_seeds(run, based_on, compiled, select=selection)
    except RecordedInputError as exc:
        raise RunNotExecutableError(str(exc)) from exc


def _cancel_orphan(run: Run, execution_id: str) -> None:
    """Cancel a QUEUED record this call created and then failed to start.

    Args:
        run: The run that owns the record.
        execution_id: The attempt id.
    """
    try:
        run.cancel(execution_id)
    except ValueError as exc:
        logger.warning(f"could not cancel orphan Execution {execution_id}: {exc}")


def _check_verbs(
    *,
    resume: bool,
    rerun: bool,
    fresh: bool,
    checkpoint: str | None,
    execution_id: str | None,
    only: Sequence[str] = (),
) -> None:
    """Reject verb combinations before any record is created.

    Raises:
        ValueError: The keywords contradict each other, or creation-time
            keywords are passed together with ``execution_id``.
    """
    if resume and rerun:
        raise ValueError(
            "resume=True and rerun=True are mutually exclusive verbs — resume "
            "creates a new Execution, rerun opens a fresh attempt."
        )
    if fresh and not rerun:
        raise ValueError(
            "fresh=True bypasses the cache for an explicit re-execution and "
            "requires rerun=True (mirroring `molab run --rerun --fresh`)."
        )
    if checkpoint is not None and not resume:
        raise ValueError("checkpoint is only valid with resume=True")
    if only and not rerun:
        raise ValueError(
            "only=(...) selects tasks for a partial rerun and requires rerun=True "
            "(mirroring `molab run --rerun --task NAME`)."
        )
    if execution_id is not None and (resume or rerun or fresh or checkpoint is not None):
        raise ValueError(
            "execution_id selects an existing Execution; resume, rerun, fresh and "
            "checkpoint are creation-time facts and cannot be passed with it"
        )


def _executor_facts(executor: str | None, max_workers: int | None) -> dict[str, JSONValue]:
    """The ``Execution.executor`` keys recording a run's task-executor choice."""
    facts: dict[str, JSONValue] = {}
    if executor is not None:
        facts[TASK_EXECUTOR_KEY] = executor
    if max_workers is not None:
        facts[TASK_MAX_WORKERS_KEY] = max_workers
    return facts


def _recorded_executor(
    record: Execution, executor: str | None, max_workers: int | None
) -> tuple[str | None, int | None]:
    """The call's executor choice, else the one the record carries."""
    recorded = record.executor or {}
    if executor is None:
        value = recorded.get(TASK_EXECUTOR_KEY)
        executor = check_executor(value if isinstance(value, str) else None)
    if max_workers is None:
        value = recorded.get(TASK_MAX_WORKERS_KEY)
        max_workers = check_max_workers(value if isinstance(value, int) else None)
    return executor, max_workers


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
    where = (
        f"Execution evidence under {run.execution_dir(exec_id)}"
        if exec_id
        else "see the run's Execution evidence"
    )
    raise RunFailedError(
        f"run {run.id} failed — {detail} "
        f"(details: {where}; retry with resume=True to continue from the "
        f"failed node, rerun=True, only=(task,) to re-execute one node from its "
        f"recorded inputs, or rerun=True to re-execute from the top)",
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
    execution_id: str | None = None,
    resume_from: Run | None = None,
    only: Sequence[str] = (),
    executor: str | None = None,
    max_workers: int | None = None,
) -> WorkflowResult:
    """Async form of :func:`execute_run` — same arguments, same result.

    Await this from inside a running event loop. :func:`execute_run` owns
    the loop and refuses that case.

    Args:
        workflow: A ``CompiledWorkflow``, or an uncompiled ``Workflow``.
        run: The workspace run to execute against.
        resume: Open a ``RESUME`` attempt. No checkpoint is required. Seeds
            are reused only when ``config_hash`` matches the predecessor.
        rerun: Open a ``RERUN`` attempt, including after success.
        fresh: Record ``bypass_cache``. Requires ``rerun=True``.
        profile_config: Profile written when this call creates the attempt.
            With ``execution_id``, ``run.start`` checks it against the record.
        checkpoint_artifact_id: Recorded on the attempt. Resume seeds come
            from the predecessor journal, not from this artifact. Only valid
            with ``resume=True``.
        execution_id: Start this pre-created QUEUED attempt. Its config and
            task selection are taken from the record. Mutually exclusive with
            the creation verbs.
        only: With ``rerun=True``, re-execute just these tasks with the
            inputs their predecessor recorded (recorded as the Execution's
            ``selected_tasks``); their downstream tasks are skipped.
        executor: How every task body runs (``"thread"`` / ``"process"`` /
            ``"inline"``), overriding the tasks' and the workflow's choice.
        max_workers: Worker threads / processes at most.

    Returns:
        The ``WorkflowResult`` — ``result.outputs`` maps task name to output.

    Raises:
        RunFailedError: A task failed (state persisted first).
        RunNotExecutableError: Status outside the verb domain (see module
            doc), or a partial rerun the predecessor's records cannot supply.
        ValueError: The keywords contradict each other, or ``only`` names a
            task the workflow does not have.
    """
    _check_verbs(
        resume=resume,
        rerun=rerun,
        fresh=fresh,
        checkpoint=checkpoint_artifact_id,
        execution_id=execution_id,
        only=only,
    )
    check_executor(executor, where="executor")
    check_max_workers(max_workers)
    compiled = _ensure_compiled(workflow)
    created_here = execution_id is None
    record = (
        _create_record(
            run,
            _select_mode(run, resume=resume, rerun=rerun),
            checkpoint_artifact_id=checkpoint_artifact_id,
            fresh=fresh,
            profile_config=profile_config,
            only=only,
            executor=_executor_facts(executor, max_workers),
        )
        if created_here
        else _queued_record(run, execution_id)
    )
    executor, max_workers = _recorded_executor(record, executor, max_workers)
    entered = False
    try:
        seeds = _attempt_seeds(run, record, compiled)
        if seeds is not None and resume_from is not None:
            raise ValueError(
                "resume_from hands another run's outputs to a fresh attempt; a resume "
                "or partial rerun seeds from this run's own records"
            )
        with run.start(
            profile_config,
            execution_id=record.id,
            workflow_hash=compiled.workflow_hash,
        ) as ctx:
            entered = True
            result = await WorkflowRuntime().execute(
                compiled,
                run_context=ctx,  # ty: ignore[invalid-argument-type]
                attempt_seeds=seeds,
                resume_from=resume_from,
                executor=executor,
                max_workers=max_workers,
            )
    except BaseException:
        if created_here and not entered:
            _cancel_orphan(run, record.id)
        raise
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
    execution_id: str | None = None,
    resume_from: Run | None = None,
    only: Sequence[str] = (),
    executor: str | None = None,
    max_workers: int | None = None,
) -> WorkflowResult:
    """Execute *workflow* against *run* in one step and return the result.

    Synchronous driver behind :meth:`Execution.execute` and :meth:`Run.execute`.
    Owns the event loop via ``asyncio.run``. The async form is
    :func:`aexecute_run`.

    Args:
        workflow: A ``CompiledWorkflow``, or an uncompiled ``Workflow``
            (compiled automatically).
        run: The workspace :class:`~molab.workspace.run.Run` to execute
            against. Its ``RunContext`` lifecycle drives the status machine
            and the ``alive`` heartbeat, exactly as under ``molab run``.
        resume: Open a new ``RESUME`` attempt. No checkpoint is required.
            Completed nodes are seeded only when this attempt's
            ``config_hash`` matches the predecessor's. Mutually exclusive
            with ``rerun``.
        rerun: Open a new ``RERUN`` attempt, including after success. With
            neither verb, a run that already has an attempt refuses (retrying
            is an explicit verb, never implicit).
        fresh: Bypass the content-addressed cache read for that attempt
            (results are still written back). Recorded as ``bypass_cache``
            on the new Execution, which the runtime reads. Requires
            ``rerun=True``.
        profile_config: Profile applied when this call creates the Execution.
            With ``execution_id`` it is not a creation fact; ``run.start``
            still checks it against the record.
        checkpoint_artifact_id: Recorded on the attempt. Resume seeds come
            from the predecessor journal, not from this artifact. Only valid
            with ``resume=True``.
        execution_id: Start this pre-created QUEUED Execution instead of
            allocating one. Its config and task selection are taken from the
            record. Mutually exclusive with the creation-time verbs.
        only: With ``rerun=True``, a partial rerun: re-execute just these
            tasks with the inputs their predecessor recorded; every other
            completed task is seeded from its record and every task
            downstream of a selected one is skipped. Recorded as the
            Execution's ``selected_tasks``.
        executor: How every task body runs — ``"thread"`` (worker threads),
            ``"process"`` (worker processes) or ``"inline"`` (one at a time
            on the engine thread) — overriding the tasks' and the workflow's
            choice. Recorded on the Execution.
        max_workers: Worker threads / processes at most (``process``
            defaults to the CPU count).

    Returns:
        The ``WorkflowResult`` — ``result.outputs`` maps task name to output.

    Raises:
        RunFailedError: A task failed (state persisted first).
        RunNotExecutableError: Status outside the verb domain (see module doc).
        ValueError: The keywords contradict each other.
        RuntimeError: Called from inside a running event loop — await
            :func:`aexecute_run`, ``run.aexecute(workflow)``, or
            ``execution.aexecute(workflow)``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "execute() was called from inside a running event loop; "
            "await run.aexecute(workflow) or execution.aexecute(workflow) instead."
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
            execution_id=execution_id,
            resume_from=resume_from,
            only=only,
            executor=executor,
            max_workers=max_workers,
        )
    )


# ── Workspace inversion seam ─────────────────────────────────────────────────


class _WorkspaceRunExecutor:
    """Implements ``molab.workspace.run.RunWorkflowExecutor``.

    ``workflow=None`` resolves through
    :func:`molab.workflow.recovery.compiled_workflow_for_run`, the same path
    the CLI and the server use.
    """

    @staticmethod
    def _resolve(run: Run, workflow: object | None) -> object:
        if workflow is not None:
            return workflow
        from .recovery import compiled_workflow_for_run

        return compiled_workflow_for_run(run)

    def execute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint: str | None = None,
        execution_id: str | None = None,
        resume_from: Run | None = None,
        only: Sequence[str] = (),
        executor: str | None = None,
        max_workers: int | None = None,
    ) -> object:
        return execute_run(
            self._resolve(run, workflow),
            run,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint_artifact_id=checkpoint,
            execution_id=execution_id,
            resume_from=resume_from,
            only=only,
            executor=executor,
            max_workers=max_workers,
        )

    @staticmethod
    def read_outputs(run: Run, execution_id: str) -> dict[str, TaskOutput]:
        """Completed-node outputs of one attempt (:func:`molab.workflow.read_outputs`)."""
        from ._engine.persistence import read_outputs as _read_outputs

        return _read_outputs(run, execution_id)

    async def aexecute(
        self,
        run: Run,
        workflow: object | None,
        *,
        resume: bool = False,
        rerun: bool = False,
        fresh: bool = False,
        checkpoint: str | None = None,
        execution_id: str | None = None,
        resume_from: Run | None = None,
        only: Sequence[str] = (),
        executor: str | None = None,
        max_workers: int | None = None,
    ) -> object:
        return await aexecute_run(
            self._resolve(run, workflow),
            run,
            resume=resume,
            rerun=rerun,
            fresh=fresh,
            checkpoint_artifact_id=checkpoint,
            execution_id=execution_id,
            resume_from=resume_from,
            only=only,
            executor=executor,
            max_workers=max_workers,
        )


def workspace_run_executor() -> RunWorkflowExecutor:
    """Return the workflow layer's implementation of the workspace run-executor seam.

    The composition root (``molab/__init__``) reaches the implementation only
    through this factory; each call returns a fresh, stateless instance.

    Returns:
        An object satisfying ``molab.workspace.run.RunWorkflowExecutor``.
    """
    return _WorkspaceRunExecutor()
