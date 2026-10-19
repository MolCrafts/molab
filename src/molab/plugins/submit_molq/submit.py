"""Submission logic using molq 0.9 types directly.

:class:`SubmitHandler` puts one attempt of a run on a scheduler queue and
records the job on ``execution.json``. :func:`reconcile_submission` is the
level-triggered terminal check a poller calls afterwards: it asks molq for the
job's current state and seals a QUEUED record the worker never started,
returning a :class:`ReconcileOutcome` rather than printing.

molq 0.9's public client is :class:`molq.Molq`. A job's identity is a
``JobRef`` (``registry_id``, ``cluster_id``, ``native_id``, ``incarnation``).
That object is stored as JSON in the attempt's ``executor["job_id"]``;
``scheduler_job_id`` is the native id. Clients are owned by the application composition root.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from molq import MolqError

from molab._typing import JSONValue
from molab.workspace.models import ComputeTarget

from .metadata import build_executor_info

if TYPE_CHECKING:
    from molq import Resources, Scheduling

    from molab.workspace.domain import Execution
    from molab.workspace.execution_repository import ExecutionRepository
    from molab.workspace.experiment import Experiment
    from molab.workspace.project import Project
    from molab.workspace.run import Run

__all__ = [
    "ReconcileOutcome",
    "SubmitHandler",
    "decode_job_ref",
    "encode_job_ref",
    "make_submit_handler",
    "reconcile_submission",
]

_REF_KEYS = ("cluster_id", "incarnation", "native_id", "registry_id")
_EXECUTION_ENV = "MOLAB_EXECUTION_ID"

_MEM_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([kmgt]i?b?)?$", re.IGNORECASE)
_MEM_SCALE = {
    "b": 1,
    "k": 1000,
    "kb": 1000,
    "ki": 1024,
    "kib": 1024,
    "m": 1000**2,
    "mb": 1000**2,
    "mi": 1024**2,
    "mib": 1024**2,
    "g": 1000**3,
    "gb": 1000**3,
    "gi": 1024**3,
    "gib": 1024**3,
    "t": 1000**4,
    "tb": 1000**4,
    "ti": 1024**4,
    "tib": 1024**4,
}
_DUR_RE = re.compile(
    r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$",
    re.IGNORECASE,
)
_TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})


def encode_job_ref(ref: dict[str, Any]) -> str:
    """Serialize a molq ``JobRef`` for ``executor["job_id"]``."""
    payload = {key: str(ref[key]) for key in _REF_KEYS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def decode_job_ref(text: str | None) -> dict[str, str] | None:
    """Parse an ``executor["job_id"]`` back into a molq ``JobRef``."""
    if not text:
        return None
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if any(not isinstance(value.get(key), str) or not value[key] for key in _REF_KEYS):
        return None
    return {key: value[key] for key in _REF_KEYS}


def _strip_none(d: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Return a copy with ``None`` values removed."""
    return {k: v for k, v in d.items() if v is not None}


def _as_int(value: JSONValue) -> int | None:
    """Read a ``JSONValue`` cell as ``int | None`` for molq resource fields."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _as_str(value: JSONValue) -> str | None:
    """Read a ``JSONValue`` cell as ``str | None`` for molq scheduling fields."""
    if isinstance(value, str):
        return value
    return None


def _memory_bytes(value: JSONValue) -> str | None:
    """Parse ``8GB`` / ``1024MB`` / ``8GiB`` into a decimal byte string."""
    text = _as_str(value)
    if text is None:
        return None
    match = _MEM_RE.match(text.strip())
    if match is None:
        return None
    unit = (match.group(2) or "b").lower()
    scale = _MEM_SCALE.get(unit)
    if scale is None:
        return None
    return str(int(float(match.group(1)) * scale))


def _duration_seconds(value: JSONValue) -> int | None:
    """Parse ``90s`` / ``30m`` / ``1h`` / ``2d`` / ``1h30m`` into seconds."""
    text = _as_str(value)
    if text is None:
        return None
    stripped = text.strip()
    if stripped.isdigit():
        return int(stripped)
    match = _DUR_RE.match(stripped)
    if match is None or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _resources(res: dict[str, JSONValue]) -> Resources | None:
    from molq import Accelerator, Resources

    gpus = _as_int(res.get("gpus"))
    accelerators = None
    if gpus:
        accelerators = (Accelerator(kind="gpu", quantity=gpus, model=_as_str(res.get("gpu_type"))),)
    built = Resources(
        cpus_per_task=_as_int(res.get("cpus")),
        memory_bytes=_memory_bytes(res.get("mem")),
        time_limit_seconds=_duration_seconds(res.get("time")),
        accelerators=accelerators,
    )
    if not built.to_wire():
        return None
    return built


def _scheduling(sched: dict[str, JSONValue], job_name: str) -> Scheduling | None:
    from molq import Scheduling

    built = Scheduling(
        name=job_name,
        partition=_as_str(sched.get("queue")),
        account=_as_str(sched.get("account")),
        qos=_as_str(sched.get("qos")),
    )
    if not built.to_wire():
        return None
    return built


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


class SubmitHandler:
    """Stateful run handler that submits jobs via molq.

    Accumulates all submitted :class:`~molab.workspace.run.Run` objects in
    :attr:`submitted_runs` so the caller can pass them to a monitor after
    dispatch completes.

    Args:
        scheduler: Scheduler name recorded on the attempt. Ignored when
            *target* is set (the target carries its own scheduler choice).
            molq 0.9 reads the scheduler from the registered cluster, not
            from this string.
        cluster: Explicit registered molq destination when no target is supplied.
        resources: Sparse dict of resource overrides (``None`` values stripped).
        scheduling: Sparse dict of scheduling overrides (``None`` values stripped).
        target: When provided, the run dir is staged in before submit and
            staged out by :func:`reconcile_submission` once the job has ended.
            When ``None`` the handler submits against the named cluster with
            the local run directory as the working directory.
        env: Environment variables exported into the job. ``None`` values
            stripped. ``MOLAB_EXECUTION_ID`` is always set.
        preamble: Shell lines run *before* the worker. A ``str`` is one line;
            a sequence is joined with newlines. When set, the job is an inline
            script (preamble + ``exec <worker>``) instead of a bare argv.
        python: The interpreter that runs the worker on the compute node.
            Defaults to this process's ``sys.executable``.
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
        destination = target.cluster_id if target is not None else cluster
        if not destination:
            raise ValueError("Submission requires an explicit molq destination")
        self._cluster: str = destination
        self._res = _strip_none(resources)
        self._sched = _strip_none(scheduling)
        self._block = block
        self._target = target
        self._env = {k: v for k, v in (env or {}).items() if v is not None}
        if isinstance(preamble, str):
            self._preamble: list[str] = [preamble]
        else:
            self._preamble = list(preamble or [])
        self.submitted_runs: list[Run] = []

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

        Anything raised before ``Cluster.submit`` returns seals the attempt
        FAILED and is re-raised. After submission the job ref is merged into
        the record's ``executor``; if a fast worker has already sealed the
        attempt, the job id is reported on stderr instead.

        Args:
            _script: Accepted for dispatcher uniformity; ignored.
            mol_run: The run to submit.
            experiment: The run's experiment; unused.
            project: The run's project (workspace root, filesystem, id).
            execution_id: An existing QUEUED attempt to submit (``e01``);
                ``None`` creates a new one.

        Raises:
            KeyError: *execution_id* names no attempt of *mol_run*.
            ValueError: *execution_id* is not QUEUED, or (no id given) the
                latest attempt is still active so no new one can be created.
            BaseException: Whatever stage-in or the scheduler raised; raised
                before ``submit`` returned, the attempt is sealed FAILED first.
        """
        from molq import Execution, ExecutionUnit, JobSpec

        from molab.workspace.domain import ExecutionMode, ExecutionStatus
        from molab.workspace.execution_repository import ExecutionRepository

        res = self._res
        sched = self._sched
        target = self._target

        job_name = f"{project.name[:20]}-{mol_run.id[:8]}"
        run_dir = Path(mol_run.run_dir)

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

        job = None
        cluster_id = self._cluster
        try:
            if target is None:
                scheduler_name = self._scheduler
                target_run_dir_ = str(run_dir)
                target_exec_dir = str(local_exec_dir)
            else:
                from molab.workspace.targets import target_definition, target_run_dir, to_filesystem

                from .staging import StagingFiles, stage_in

                definition = target_definition(target)
                cluster_id = str(definition["id"])
                target = target.model_copy(update={"cluster_id": cluster_id})
                repo.update_operational(
                    attempt_id,
                    executor={
                        "registry_id": target.registry_id,
                        "cluster_id": cluster_id,
                        "scratch_root": target.scratch_root,
                    },
                )
                remote_transport = cast(StagingFiles, to_filesystem(target))
                scheduler_name = str(definition["scheduler"])
                target_run_dir_ = target_run_dir(target, project.workspace, mol_run)
                repo.update_operational(attempt_id, executor={"remote_run_dir": target_run_dir_})
                target_exec_dir = f"{target_run_dir_}/executions/{attempt_id}"
                stage_in(remote_transport, mol_run, target, attempt_id, destination=target_run_dir_)

            worker_argv = [
                self._python,
                "-m",
                "molab.cli",
                "execute",
                target_run_dir_,
                "--execution-id",
                attempt_id,
            ]
            env = dict(self._env)
            env[_EXECUTION_ENV] = attempt_id
            if self._preamble:
                worker_cmd = " ".join(shlex.quote(a) for a in worker_argv)
                script_text = "\n".join([*self._preamble, f"exec {worker_cmd}"])
                unit = ExecutionUnit.script("main", script_text, cwd=target_exec_dir, env=env)
            else:
                unit = ExecutionUnit.argv("main", worker_argv, cwd=target_exec_dir, env=env)
            spec = JobSpec(
                execution=Execution(units=(unit,), cwd=target_exec_dir, env=env),
                resources=_resources(res),
                scheduling=_scheduling(sched, job_name),
            )
            from molab.workspace.connection import get_client

            job = (
                get_client(target.registry_id if target is not None else None)
                .cluster(cluster_id)
                .submit(spec)
            )
        except BaseException as exc:
            if job is None and isinstance(exc, MolqError) and exc.outcome == "unknown":
                repo.update_operational(attempt_id, executor={"submission_outcome": "unknown"})
            elif job is None:
                repo.seal(
                    attempt_id,
                    ExecutionStatus.FAILED,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            raise

        ref = dict(job.ref)
        native_id = str(ref.get("native_id") or "")
        executor_info = build_executor_info(
            scheduler=scheduler_name,
            cluster_name=cluster_id,
            job_id=encode_job_ref(ref),
            scheduler_job_id=native_id or None,
        )
        try:
            repo.update_operational(attempt_id, executor=executor_info)
        except ValueError:
            current = repo.get(attempt_id)
            if current.sealed_at is None:
                raise
            print(
                f"molab: job {native_id or encode_job_ref(ref)} submitted for run {mol_run.id} "
                f"attempt {attempt_id}, which was already {current.status.value}; "
                "job id not recorded",
                file=sys.stderr,
            )
        self.submitted_runs.append(mol_run)


def reconcile_submission(mol_run: Run, execution_id: str) -> ReconcileOutcome:
    """Check a QUEUED molq-submitted attempt against its job and seal it if it never started.

    Level-triggered: every call asks molq for the job's state now
    (``Job.status``) instead of waiting for an event. Only a QUEUED record
    can be sealed here. A RUNNING record whose worker died is left to the
    reaper.

    The stored ``job_id`` is a JSON ``JobRef``. While the snapshot is not
    terminal nothing changes. Once it is, a remote attempt is staged out
    first; a record still QUEUED is sealed CANCELLED for a cancelled job and
    FAILED otherwise, with error type ``SchedulerJobEndedBeforeStart``. A
    remote record that cannot be read is left QUEUED. A molq ``succeeded``
    snapshot still seals a still-queued attempt FAILED: the worker never
    claimed the record.

    Idempotent. An expected failure — ``MolqError``, staging
    ``TransportError``, ``ValueError``, ``OSError``, ``KeyError`` — comes
    back as :attr:`ReconcileOutcome.error`. Anything else propagates.

    Args:
        mol_run: The run the attempt belongs to.
        execution_id: The attempt to check (``e01``).

    Returns:
        The attempt's record after the check, and the failure, if any.

    Raises:
        KeyError: No attempt ``execution_id`` exists under *mol_run*.
    """
    from molq import MolqError

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
    if executor.get("transfer_outcome") == "unknown":
        return ReconcileOutcome(
            record=record,
            error="Previous file transfer outcome is unknown; explicit operator review is required",
        )
    job_id = executor.get("job_id")
    if executor.get("backend") != "molq" or not isinstance(job_id, str) or not job_id:
        return ReconcileOutcome(record=record)
    ref = decode_job_ref(job_id)
    if ref is None:
        return ReconcileOutcome(
            record=record,
            error=(
                f"could not reconcile run {mol_run.id} attempt {execution_id}: "
                f"ValueError: executor job_id is not a molq JobRef"
            ),
        )

    try:
        target_name = executor.get("target")
        if isinstance(target_name, str):
            target = ComputeTarget.model_validate(
                {
                    "name": target_name,
                    "registry_id": executor.get("registry_id"),
                    "cluster_id": executor.get("cluster_id"),
                    "scratch_root": executor.get("scratch_root"),
                }
            )
            if target.cluster_id != ref["cluster_id"] or target.registry_id != ref["registry_id"]:
                raise ValueError("Execution destination differs from its molq job reference")
            transport = cast(staging.StagingFiles, targets.to_filesystem(target))
        else:
            target = None
            transport = None

        from molab.workspace.connection import get_client

        status = get_client(ref["registry_id"]).job(ref).status()
        snapshots = status.get("snapshots") or []
        if not snapshots:
            raise MolqError("JOB_NOT_FOUND", f"job {job_id} returned no snapshot")
        snapshot = snapshots[0]
        state = str(snapshot.get("state") or "unknown")
        if not snapshot.get("terminal") and state not in _TERMINAL_STATES:
            return ReconcileOutcome(record=record)

        if target is None or transport is None:
            authoritative = True
        else:
            authoritative = staging.stage_out(transport, mol_run, target, execution_id)
        if authoritative:
            _seal_if_unstarted(repo, execution_id, state)
    except (MolqError, ValueError, OSError, KeyError) as exc:
        if isinstance(exc, MolqError) and exc.outcome == "unknown":
            repo.update_operational(execution_id, executor={"transfer_outcome": "unknown"})
        return ReconcileOutcome(
            record=repo.get(execution_id),
            error=(
                f"could not reconcile run {mol_run.id} attempt {execution_id}: "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    return ReconcileOutcome(record=repo.get(execution_id))


def _seal_if_unstarted(repo: ExecutionRepository, execution_id: str, state: str) -> None:
    """Seal an attempt the worker never started, once its job has ended."""
    from molab.workspace.domain import ExecutionStatus

    current = repo.get(execution_id)
    if current.status is not ExecutionStatus.QUEUED:
        return
    repo.seal(
        execution_id,
        ExecutionStatus.CANCELLED if state == "cancelled" else ExecutionStatus.FAILED,
        error={
            "type": "SchedulerJobEndedBeforeStart",
            "message": f"scheduler reported {state} before the worker started",
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
    called as ``(script, mol_run, experiment, project, *, execution_id=...)``.
    ``None`` values in *resources* and *scheduling* are stripped.

    Args:
        scheduler: Scheduler name recorded on the attempt.
        cluster: Registered molq destination name or ID, required when *target*
            does not provide a destination.
        resources: Resource options dict (``None`` values are stripped).
        scheduling: Scheduling options dict (``None`` values are stripped).
        target: Optional compute target. When set, the run dir is staged
            in and out across the target's transport.
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
