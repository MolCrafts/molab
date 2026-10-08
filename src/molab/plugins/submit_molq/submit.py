"""Submission logic using molq types directly.

:class:`SubmitHandler` puts one attempt of a run on a scheduler queue and
records the job on ``execution.json``. :func:`reconcile_submission` is the
level-triggered terminal check a poller calls afterwards: it asks molq for the
job's current state and seals a QUEUED record the worker never started,
returning a :class:`ReconcileOutcome` rather than printing.
"""

from __future__ import annotations

import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from molab._typing import JSONValue

from .metadata import build_executor_info

if TYPE_CHECKING:
    from molq import Duration, JobExecution, JobHandle, JobState, Memory, Script, Submitor

    class _CmdKwargs(TypedDict, total=False):
        """The mutually-exclusive command channel passed to ``submit_job``.

        Matches molq's ``argv: list[str] | None`` / ``script: Script | None``
        parameter types so the ``**`` spread type-checks against the exact
        keyword each branch fills (a plain ``dict`` would widen every keyword).
        """

        argv: list[str]
        script: Script

    from molab.workspace import ComputeTarget
    from molab.workspace.domain import Execution
    from molab.workspace.execution_repository import ExecutionRepository
    from molab.workspace.experiment import Experiment
    from molab.workspace.project import Project
    from molab.workspace.run import Run

__all__ = [
    "DEFAULT_CLUSTER_NAME",
    "ReconcileOutcome",
    "SubmitHandler",
    "make_submit_handler",
    "reconcile_submission",
]

DEFAULT_CLUSTER_NAME = "default"
"""molq cluster name used when none is given at submit or recorded on the attempt."""


@dataclass(frozen=True)
class ReconcileOutcome:
    """What one :func:`reconcile_submission` call found.

    Attributes:
        record: The attempt's record after the check (unchanged unless it was
            sealed or merged).
        error: ``None`` when the check completed; otherwise one line naming
            the run, the attempt and the failure
            (``could not reconcile run <id> attempt eNN: <Type>: <message>``),
            with the record left as it was.
    """

    record: Execution
    error: str | None = None


def _strip_none(d: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Return a copy with ``None`` values removed."""
    return {k: v for k, v in d.items() if v is not None}


def _as_int(value: JSONValue) -> int | None:
    """Read a ``JSONValue`` cell as ``int | None`` for molq resource fields."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _as_str(value: JSONValue) -> str | None:
    """Read a ``JSONValue`` cell as ``str | None`` for molq scheduling fields."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _parse_memory(value: JSONValue) -> Memory | None:
    """Parse a ``JSONValue`` cell as a molq ``Memory`` literal (e.g. ``'8GB'``)."""
    text = _as_str(value)
    if text is None:
        return None
    from molq import Memory as _Memory

    return _Memory.parse(text)


def _parse_duration(value: JSONValue) -> Duration | None:
    """Parse a ``JSONValue`` cell as a molq ``Duration`` literal (e.g. ``'1h'``)."""
    text = _as_str(value)
    if text is None:
        return None
    from molq import Duration as _Duration

    return _Duration.parse(text)


class SubmitHandler:
    """Stateful run handler that submits jobs via molq.

    Accumulates all submitted :class:`~molab.workspace.run.Run` objects in
    :attr:`submitted_runs` so the caller can pass them to a monitor after
    dispatch completes.

    Args:
        scheduler: molq scheduler backend name. Ignored when *target* is set
            (the target carries its own scheduler choice).
        cluster: molq cluster name (``None`` → :data:`DEFAULT_CLUSTER_NAME`).
        resources: Sparse dict of resource overrides (``None`` values stripped).
        scheduling: Sparse dict of scheduling overrides (``None`` values stripped).
        target: When provided, jobs are routed through the target's transport
            and scheduler; the run dir is staged in before submit and staged
            out by :func:`reconcile_submission` once the job has ended.  When
            ``None`` the handler dispatches
            via molq's default ``LocalTransport`` against the workspace's
            local filesystem (the ``--scheduler X`` CLI path with no target).
        env: Environment variables exported into the batch script before the
            worker runs (e.g. ``LD_LIBRARY_PATH``). ``None`` values stripped.
        preamble: Shell lines run *before* the worker, for environments that
            need setup the scheduler cannot express as resources — ``module
            load``, ``source venv/bin/activate``, etc. A ``str`` is treated as
            one line; a sequence is joined with newlines. When set, the job is
            submitted as an inline script (preamble + ``exec <worker>``) instead
            of a bare ``argv``.
        python: The interpreter that runs the worker on the compute node.
            Defaults to this process's ``sys.executable``, which is wrong when
            the nodes have another architecture or environment than the
            submitting host (an x86 login node in front of aarch64 GPUs).
    """

    def __init__(
        self,
        *,
        scheduler: str,
        cluster: str | None,
        resources: dict[str, JSONValue],
        scheduling: dict[str, JSONValue],
        block: bool = False,
        target: ComputeTarget | None = None,
        env: dict[str, str] | None = None,
        preamble: str | Sequence[str] | None = None,
        python: str | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._python = python or sys.executable
        self._cluster = cluster or DEFAULT_CLUSTER_NAME
        self._res = _strip_none(resources)
        self._sched = _strip_none(scheduling)
        self._block = block
        self._target = target
        self._env = {k: v for k, v in (env or {}).items() if v is not None}
        if isinstance(preamble, str):
            self._preamble: list[str] = [preamble]
        else:
            self._preamble = list(preamble or [])
        # ``_handles`` stores molq ``JobExecution`` handles; ``_submitor`` is the
        # active molq ``Submitor`` context. Typed via TYPE_CHECKING string refs
        # so import order stays clean.
        self._handles: list[JobExecution] = []
        self._submitor: Submitor | None = None
        self.submitted_runs: list[Run] = []

    # ------------------------------------------------------------------
    # Callable protocol

    def __call__(
        self,
        _script: str | Path | None,
        mol_run: Run,
        experiment: Experiment,  # noqa: ARG002
        project: Project,
        *,
        execution_id: str | None = None,
    ) -> None:
        """Submit one attempt of *mol_run* to the scheduler.

        The attempt is resolved before any transport or scheduler call. With
        no *execution_id* a new QUEUED ``eNN`` is created through
        ``Run._create_execution`` (``initial`` for the first attempt, else
        ``rerun`` based on the latest one); with an id, that attempt must
        already exist and still be QUEUED — ids are allocated only by the
        workspace, never here.

        Anything raised before ``submit_job`` returns seals the attempt
        FAILED and is re-raised. After submission the job ids are merged into
        the record's ``executor``; if a fast worker has already sealed the
        attempt, the job id is reported on stderr instead. The job's end is
        not observed here: :func:`reconcile_submission` checks it whenever a
        poller asks.

        Args:
            _script: Accepted for dispatcher uniformity; ignored (the worker
                rebuilds the run from its directory).
            mol_run: The run to submit.
            experiment: The run's experiment; unused.
            project: The run's project (workspace root, filesystem, id).
            execution_id: An existing QUEUED attempt to submit (``e01``);
                ``None`` creates a new one.

        Raises:
            KeyError: *execution_id* names no attempt of *mol_run*.
            ValueError: *execution_id* is not QUEUED, or (no id given) the
                latest attempt is still active so no new one can be created.
            BaseException: Whatever the transport, stage-in or scheduler raised
                (or an interrupt); raised before ``submit_job`` returned, the
                attempt is sealed FAILED first.
        """
        from molq import (
            Cluster,
            JobExecution,
            JobResources,
            JobScheduling,
            Script,
            Submitor,
        )

        from molab.workspace.domain import ExecutionMode, ExecutionStatus
        from molab.workspace.execution_repository import ExecutionRepository

        res = self._res
        sched = self._sched
        target = self._target

        job_name = f"{project.name[:20]}-{mol_run.id[:8]}"
        run_dir = Path(mol_run.run_dir)

        # Resolve the attempt before touching any transport or scheduler.
        if execution_id is None:
            prior = mol_run.executions
            record = mol_run._create_execution(
                mode=ExecutionMode.RERUN if prior else ExecutionMode.INITIAL,
                predecessor=prior[-1].id if prior else None,
                executor={"backend": "molq", "target": target.name if target else None},
                environment={"submit_cwd": str(Path.cwd().resolve())},
            )
        else:
            record = mol_run.execution(execution_id)
            if record.status is not ExecutionStatus.QUEUED:
                raise ValueError(
                    f"attempt {record.id!r} of run {mol_run.id!r} is {record.status.value}, "
                    "not queued"
                )
        attempt_id = record.id
        local_exec_dir = run_dir / "executions" / attempt_id
        local_exec_dir.mkdir(parents=True, exist_ok=True)

        repo = ExecutionRepository(
            project.workspace.root,
            mol_run.run_dir,
            run_id=mol_run.id,
            project_id=project.id,
            fs=project.workspace.fs,
        )

        job: JobHandle | None = None
        try:
            if target is None:
                # No-target path: rely on molq's default LocalTransport.
                transport = None
                scheduler_name = self._scheduler
                target_run_dir_ = str(run_dir)
                target_exec_dir = str(local_exec_dir)
            else:
                from molab.workspace.targets import target_run_dir, to_transport

                from .staging import stage_in

                remote_target = target
                remote_transport = to_transport(remote_target)
                transport = remote_transport
                scheduler_name = remote_target.scheduler
                target_run_dir_ = target_run_dir(remote_target, project.workspace, mol_run)
                target_exec_dir = f"{target_run_dir_}/executions/{attempt_id}"
                remote_transport.mkdir(target_exec_dir, parents=True, exist_ok=True)
                stage_in(remote_transport, mol_run, remote_target, attempt_id)

            jobs_dir = f"{target_exec_dir}/jobs"
            # mkdir for the local case is implicit in Submitor; for remote case
            # we already created target_exec_dir, but we still need the jobs
            # subdir to exist before molq writes its manifest.
            if transport is not None:
                transport.mkdir(jobs_dir, parents=True, exist_ok=True)
            else:
                Path(jobs_dir).mkdir(parents=True, exist_ok=True)

            with Submitor(
                Cluster(
                    name=self._cluster,
                    scheduler=scheduler_name,
                    transport=transport,
                ),
                jobs_dir=jobs_dir,
            ) as submitor:
                worker_argv = [
                    self._python,
                    "-m",
                    "molab.cli",
                    "execute",
                    target_run_dir_,
                    "--execution-id",
                    attempt_id,
                ]
                # With a preamble (module load / source venv / …) the worker can't
                # be a bare argv: wrap it in an inline script so the setup lines run
                # first, then ``exec`` the worker so it inherits the job's PID.
                # A TypedDict (not a plain dict) so the ``**cmd_kwargs`` spread maps
                # each key to molq's exact parameter type (``argv`` / ``script``).
                cmd_kwargs: _CmdKwargs
                if self._preamble:
                    worker_cmd = " ".join(shlex.quote(a) for a in worker_argv)
                    script_text = "\n".join([*self._preamble, f"exec {worker_cmd}"])
                    cmd_kwargs = {"script": Script.inline(script_text)}
                else:
                    cmd_kwargs = {"argv": worker_argv}

                job = submitor.submit_job(
                    **cmd_kwargs,
                    resources=JobResources(
                        cpu_count=_as_int(res.get("cpus")),
                        memory=_parse_memory(res.get("mem")),
                        gpu_count=_as_int(res.get("gpus")),
                        gpu_type=_as_str(res.get("gpu_type")),
                        time_limit=_parse_duration(res.get("time")),
                    ),
                    scheduling=JobScheduling(
                        partition=_as_str(sched.get("queue")),
                        account=_as_str(sched.get("account")),
                        qos=_as_str(sched.get("qos")),
                    ),
                    execution=JobExecution(
                        job_name=job_name,
                        cwd=target_exec_dir,
                        env=self._env or None,
                    ),
                    metadata={
                        "run_id": mol_run.id,
                        "run_dir": target_run_dir_,
                        "execution_id": attempt_id,
                    },
                )
        except BaseException as exc:
            # Before ``submit_job`` returned nothing is queued, so the attempt
            # failed — whatever ended it, KeyboardInterrupt included. After it
            # returned the job is real: do not seal.
            if job is None:
                repo.seal(
                    attempt_id,
                    ExecutionStatus.FAILED,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            raise

        executor_info = build_executor_info(
            scheduler=scheduler_name,
            cluster_name=self._cluster,
            job_id=job.job_id,
            scheduler_job_id=job.scheduler_job_id,
        )
        try:
            repo.update_operational(attempt_id, executor=executor_info)
        except ValueError:
            current = repo.get(attempt_id)
            if current.sealed_at is None:
                raise
            print(
                f"molab: job {job.job_id} submitted for run {mol_run.id} attempt {attempt_id}, "
                f"which was already {current.status.value}; job id not recorded",
                file=sys.stderr,
            )
        self.submitted_runs.append(mol_run)


def reconcile_submission(mol_run: Run, execution_id: str) -> ReconcileOutcome:
    """Check a QUEUED molq-submitted attempt against its job and seal it if it never started.

    Level-triggered: every call asks molq for the job's state now
    (``Submitor.refresh_job``) instead of waiting for an event, so any poller
    (``molab run --block``, ``molab monitor``) can call it repeatedly. Only a
    QUEUED record can be sealed here, so only a QUEUED record reaches molq: a
    RUNNING or sealed record, a record not submitted through molq, or one with
    no recorded ``job_id`` is returned unchanged without contacting molq or a
    transport. A RUNNING record whose worker died is left to the reaper.

    The ``Submitor`` is rebuilt from the record's ``executor``
    (``cluster_name`` / ``scheduler`` / ``target`` / ``job_id``), with the same
    jobs directory the submission used. While the job is not terminal nothing
    changes. Once it is, a remote attempt is staged out first; when the local
    record then reflects the worker's (always, for a local submission) a record
    still QUEUED is sealed CANCELLED for a cancelled job and FAILED otherwise,
    with error type ``SchedulerJobEndedBeforeStart``. A remote record that
    cannot be read is left QUEUED.

    Single-host: molq's job store is per user and host, so the recorded
    ``job_id`` resolves only in the submitting user's molq ``jobs.db``. A
    monitor running as another user or on another host gets
    ``JobNotFoundError``, which is reported through
    :attr:`ReconcileOutcome.error` and leaves the record QUEUED.

    Idempotent: a repeated call finds the record sealed and returns it. There
    is no time-based reaping — a record whose job no one polls stays QUEUED;
    the operator remedy is ``molab runs cancel <run-id>``. Nothing is printed
    (a caller may be drawing a full-screen view): an expected failure —
    querying molq (``TransportError`` / ``JobNotFoundError``), reaching the
    target (``OSError``), resolving it (``KeyError``) or merging the remote
    record (``ValueError``, pydantic ``ValidationError`` included) — comes
    back as :attr:`ReconcileOutcome.error` with the record left as it was.
    Anything else is a programming error and propagates.

    Args:
        mol_run: The run the attempt belongs to.
        execution_id: The attempt to check (``e01``).

    Returns:
        The attempt's record after the check, and the failure, if any.

    Raises:
        KeyError: No attempt ``execution_id`` exists under *mol_run*.
    """
    from molq import Cluster, JobNotFoundError, Submitor
    from molq.transport import TransportError

    from molab.workspace import targets
    from molab.workspace.domain import ExecutionStatus
    from molab.workspace.execution_repository import ExecutionRepository

    from . import staging

    project = mol_run.experiment.project
    workspace = project.workspace
    repo = ExecutionRepository(
        workspace.root,
        mol_run.run_dir,
        run_id=mol_run.id,
        project_id=project.id,
        fs=workspace.fs,
    )
    record = repo.get(execution_id)
    if record.status is not ExecutionStatus.QUEUED:
        return ReconcileOutcome(record=record)
    executor = record.executor
    job_id = executor.get("job_id")
    if executor.get("backend") != "molq" or not isinstance(job_id, str) or not job_id:
        return ReconcileOutcome(record=record)

    try:
        scheduler = executor.get("scheduler")
        if not isinstance(scheduler, str):
            raise ValueError(f"executor records no scheduler for job {job_id}")
        cluster_name = executor.get("cluster_name")
        target_name = executor.get("target")
        if isinstance(target_name, str):
            target = targets.resolve_compute_target(workspace, target_name)
            transport = targets.to_transport(target)
            run_dir = targets.target_run_dir(target, workspace, mol_run)
        else:
            target = None
            transport = None
            run_dir = str(mol_run.run_dir)
        exec_dir = f"{run_dir}/executions/{execution_id}"

        with Submitor(
            Cluster(
                name=cluster_name if isinstance(cluster_name, str) else DEFAULT_CLUSTER_NAME,
                scheduler=scheduler,
                transport=transport,
            ),
            jobs_dir=f"{exec_dir}/jobs",
        ) as submitor:
            job = submitor.refresh_job(job_id)
        if not job.state.is_terminal:
            return ReconcileOutcome(record=record)

        if target is None or transport is None:
            authoritative = True
        else:
            authoritative = staging.stage_out(transport, mol_run, target, execution_id)
        if authoritative:
            _seal_if_unstarted(repo, execution_id, job.state)
    except (TransportError, JobNotFoundError, ValueError, OSError, KeyError) as exc:
        return ReconcileOutcome(
            record=repo.get(execution_id),
            error=(
                f"could not reconcile run {mol_run.id} attempt {execution_id}: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    return ReconcileOutcome(record=repo.get(execution_id))


def _seal_if_unstarted(repo: ExecutionRepository, execution_id: str, state: JobState) -> None:
    """Seal an attempt the worker never started, once its job has ended.

    Called by :func:`reconcile_submission` once molq reports the job terminal
    and the local record reflects the worker's. A record still QUEUED means
    the job ended before the worker claimed it: it is sealed CANCELLED for a
    cancelled job, FAILED otherwise, with error type
    ``SchedulerJobEndedBeforeStart``. A RUNNING record (the reaper's case) or
    a sealed one is left alone, so a repeated check is a no-op.

    Args:
        repo: The run's execution repository.
        execution_id: The attempt the job was submitted for (``e01``).
        state: The terminal molq state the scheduler reported.
    """
    from molq import JobState

    from molab.workspace.domain import ExecutionStatus

    current = repo.get(execution_id)
    if current.status is not ExecutionStatus.QUEUED:
        return
    repo.seal(
        execution_id,
        ExecutionStatus.CANCELLED if state is JobState.CANCELLED else ExecutionStatus.FAILED,
        error={
            "type": "SchedulerJobEndedBeforeStart",
            "message": f"scheduler reported {state.value} before the worker started",
        },
    )


def make_submit_handler(
    *,
    scheduler: str,
    cluster: str | None,
    resources: dict[str, JSONValue],
    scheduling: dict[str, JSONValue],
    target: ComputeTarget | None = None,
    preamble: str | Sequence[str] | None = None,
    python: str | None = None,
    env: dict[str, str] | None = None,
) -> SubmitHandler:
    """Return a :class:`SubmitHandler` configured for the given scheduler.

    The handler satisfies :class:`molab.cli.workspace.run.RunHandler`: it is
    called as ``(script, mol_run, experiment, project, *, execution_id=...)``,
    where ``execution_id`` names the QUEUED Execution the dispatcher created
    just before the call (``None`` only for ``--resume``). The leading
    ``script`` is accepted for uniformity with the dispatcher and
    intentionally ignored; the worker rebuilds the run from ``run_dir``.

    All ``None`` values in *resources* and *scheduling* are stripped so that
    molq passes them through as unset, letting each scheduler use its own
    defaults.

    Args:
        scheduler: molq scheduler backend name.
        cluster: molq cluster name; ``None`` defaults to
            :data:`DEFAULT_CLUSTER_NAME`.
        resources: Resource options dict (``None`` values are stripped).
        scheduling: Scheduling options dict (``None`` values are stripped).
        target: Optional :class:`~molab.workspace.ComputeTarget` — when set,
            jobs route through the target's transport + scheduler and the run
            dir is staged in/out across the transport.
        preamble: Shell lines the job runs before the worker.
        python: The worker's interpreter on the compute node.
        env: Extra environment for the worker.

    Returns:
        Configured :class:`SubmitHandler` instance.
    """
    return SubmitHandler(
        scheduler=scheduler,
        cluster=cluster,
        resources=resources,
        scheduling=scheduling,
        target=target,
        preamble=preamble,
        python=python,
        env=env,
    )
