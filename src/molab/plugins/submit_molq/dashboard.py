"""Read-only view of molq 0.9 clusters for the Remote Operations UI.

Walks ``clusters.list`` and each cluster's ``jobs.list`` snapshots and shapes
them into the same DTOs the server schema already maps. molq 0.9 has no job
store, no status transitions, and no per-job command string, so transitions
stay empty and ``command_display`` stays ``None``.

Tests replace :func:`molq_session`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any, Protocol, cast

# ── State buckets ──────────────────────────────────────────────────────────
# molq 0.9 states: queued, running, succeeded, failed, cancelled, timed_out,
# unknown. ``unknown`` is uncounted.

_PENDING_STATES = frozenset({"queued"})
_RUNNING_STATES = frozenset({"running"})
_FAILED_STATES = frozenset({"failed", "timed_out", "cancelled"})
_SUCCEEDED_STATES = frozenset({"succeeded"})

_WAIT_WINDOW_SECONDS = 24 * 60 * 60
_LOG_POLL_SECONDS = 0.25
_LOG_IDLE_TIMEOUT_SECONDS = 5 * 60


@dataclass(frozen=True)
class TargetSummary:
    name: str
    scheduler: str
    cluster_name: str | None
    jobs_dir: str | None
    healthy: bool
    health_reason: str | None
    active_jobs: int


@dataclass(frozen=True)
class JobSummary:
    target: str
    job_id: str
    scheduler_job_id: str | None
    cluster_name: str | None
    scheduler: str | None
    name: str | None
    state: str
    submitted_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    duration_seconds: float | None
    cwd: str | None


@dataclass(frozen=True)
class JobTransition:
    timestamp: datetime
    from_state: str | None
    to_state: str
    reason: str | None


@dataclass(frozen=True)
class JobDetail:
    summary: JobSummary
    failure_reason: str | None
    metadata: dict[str, str]
    command_display: str | None
    transitions: tuple[JobTransition, ...]
    upstream_total: int
    upstream_satisfied: int
    downstream_total: int


@dataclass(frozen=True)
class QueueStats:
    running: int = 0
    pending: int = 0
    failed: int = 0
    succeeded: int = 0
    avg_wait_seconds: float | None = None


@dataclass(frozen=True)
class JobsPage:
    jobs: tuple[JobSummary, ...] = field(default_factory=tuple)
    stats: QueueStats = field(default_factory=QueueStats)


class _QueueCluster(Protocol):
    def list(
        self, *, states: Sequence[str] | None = None, name: str | None = None
    ) -> dict[str, Any]: ...


class _LogJob(Protocol):
    def status(self, *, consistency: str = "live", max_age: float = 5) -> dict[str, Any]: ...

    def logs(
        self, *, stream: str = "stdout", offset: int = 0, limit: int = 262144
    ) -> dict[str, Any]: ...


class _ClusterRegistry(Protocol):
    def list(self) -> Sequence[dict[str, Any]]: ...


class _DashboardClient(Protocol):
    clusters: _ClusterRegistry

    def cluster(self, name: str) -> _QueueCluster: ...

    def job(self, ref: dict[str, str]) -> _LogJob: ...


@contextmanager
def molq_session(config_path: str | Path | None = None) -> Generator[_DashboardClient]:
    """Open one molq client. ``config_path`` selects the temporary serve config."""
    from molq import Molq

    if config_path is None:
        from molab.workspace.connection import get_client

        yield cast(_DashboardClient, get_client())
        return
    kwargs: dict[str, Any] = {}
    if config_path is not None:
        kwargs["config"] = config_path
    with Molq(**kwargs) as client:
        yield client


def _queue_snapshots(
    mq: _DashboardClient, name: str, *, states: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """Reject incomplete queue observations before deriving health or absence."""
    from molq import MolqError

    page = mq.cluster(name).list(states=states)
    if (page.get("coverage") or {}).get("errors"):
        raise MolqError("QUERY_INCOMPLETE", f"Incomplete queue response from {name}")
    return list(page.get("snapshots") or [])


def list_targets(config_path: str | Path | None = None) -> list[TargetSummary]:
    """Return one :class:`TargetSummary` per registered molq cluster.

    Per-cluster queue failures are swallowed and surfaced as ``healthy=False``.
    """
    with molq_session(config_path) as mq:
        records = list(mq.clusters.list() or [])
        targets: list[TargetSummary] = []
        for record in records:
            name = str(record.get("name") or "")
            active = 0
            healthy = True
            reason: str | None = None
            try:
                active = len(_queue_snapshots(mq, name, states=["queued", "running"]))
            except Exception as exc:
                healthy = False
                reason = f"{type(exc).__name__}: {exc}"
            cluster_id = record.get("id")
            target_root = record.get("target_root")
            targets.append(
                TargetSummary(
                    name=name,
                    scheduler=str(record.get("scheduler") or ""),
                    cluster_name=str(cluster_id) if cluster_id else name or None,
                    jobs_dir=str(target_root) if target_root else None,
                    healthy=healthy,
                    health_reason=reason,
                    active_jobs=active,
                )
            )
    return targets


def list_jobs(
    target: str | None = None,
    *,
    include_terminal: bool = True,
    limit: int = 200,
    config_path: str | Path | None = None,
) -> list[JobSummary]:
    """List jobs across one or all registered clusters.

    Sorted by ``submitted_at`` descending; jobs without a submitted timestamp
    sort last. ``job_id`` is the native scheduler id.
    """
    if limit <= 0:
        return []

    with molq_session(config_path) as mq:
        records = list(mq.clusters.list() or [])
        by_name = {str(record.get("name") or ""): record for record in records}
        if target is not None:
            if target not in by_name:
                raise KeyError(f"Unknown molq cluster: {target!r}")
            names = [target]
        else:
            names = list(by_name)

        states = None if include_terminal else ["queued", "running"]
        collected: list[JobSummary] = []
        for name in names:
            snapshots = _queue_snapshots(mq, name, states=states)
            record = by_name[name]
            for snapshot in snapshots:
                collected.append(_to_summary(name, record, snapshot))

    collected.sort(
        key=lambda job: job.submitted_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return collected[:limit]


def get_job(
    target: str,
    job_id: str,
    *,
    config_path: str | Path | None = None,
) -> JobDetail:
    """Return a :class:`JobDetail` for ``(target, job_id)``.

    ``job_id`` is the native scheduler id, or a JSON ``JobRef``.

    Raises:
        KeyError: ``target`` is not a registered cluster.
        MolqError: the job is not in that cluster's queue or history sample.
    """
    from molq import MolqError

    with molq_session(config_path) as mq:
        records = list(mq.clusters.list() or [])
        record = next((item for item in records if item.get("name") == target), None)
        if record is None:
            raise KeyError(f"Unknown molq cluster: {target!r}")
        snapshot = _find_snapshot(mq, target, job_id)
        if snapshot is None:
            raise MolqError("JOB_NOT_FOUND", f"job {job_id} not found on {target}")
        summary = _to_summary(target, record, snapshot)
        error = snapshot.get("error")
        failure = None
        if isinstance(error, dict) and error.get("message"):
            failure = str(error["message"])
        return JobDetail(
            summary=summary,
            failure_reason=failure,
            metadata=_metadata(snapshot),
            command_display=None,
            transitions=(),
            upstream_total=0,
            upstream_satisfied=0,
            downstream_total=0,
        )


def compute_stats(jobs: list[JobSummary]) -> QueueStats:
    """Bucket *jobs* into running/pending/failed/succeeded counts plus avg wait.

    ``avg_wait_seconds`` is the mean of ``started_at - submitted_at`` over jobs
    where both timestamps are present and ``submitted_at`` falls within the last
    24 hours. Returns ``None`` when no eligible jobs exist.
    """
    running = pending = failed = succeeded = 0
    waits: list[float] = []
    cutoff = datetime.now(UTC).timestamp() - _WAIT_WINDOW_SECONDS

    for job in jobs:
        state = job.state
        if state in _RUNNING_STATES:
            running += 1
        elif state in _PENDING_STATES:
            pending += 1
        elif state in _FAILED_STATES:
            failed += 1
        elif state in _SUCCEEDED_STATES:
            succeeded += 1

        if (
            job.submitted_at is not None
            and job.started_at is not None
            and job.submitted_at.timestamp() >= cutoff
        ):
            delta = (job.started_at - job.submitted_at).total_seconds()
            if delta >= 0:
                waits.append(delta)

    avg_wait = mean(waits) if waits else None
    return QueueStats(
        running=running,
        pending=pending,
        failed=failed,
        succeeded=succeeded,
        avg_wait_seconds=avg_wait,
    )


def fetch_page(
    target: str | None,
    *,
    include_terminal: bool = True,
    limit: int = 200,
    config_path: str | Path | None = None,
) -> JobsPage:
    """Convenience wrapper: list jobs and compute stats together."""
    jobs = list_jobs(
        target,
        include_terminal=include_terminal,
        limit=limit,
        config_path=config_path,
    )
    return JobsPage(jobs=tuple(jobs), stats=compute_stats(jobs))


async def tail_log(
    target: str,
    job_id: str,
    *,
    stream: str = "stdout",
    config_path: str | Path | None = None,
) -> AsyncIterator[str]:
    """Yield newline-terminated chunks from a job's stdout or stderr.

    Reads ``logs.read`` until the snapshot is terminal or the stream is idle
    for :data:`_LOG_IDLE_TIMEOUT_SECONDS`. Yields a final ``"[stream closed]"``.
    """
    if stream not in ("stdout", "stderr"):
        raise ValueError(f"stream must be 'stdout' or 'stderr', got {stream!r}")

    from molq import MolqError

    session = molq_session(config_path)
    mq = session.__enter__()
    try:
        snapshot = _find_snapshot(mq, target, job_id)
        if snapshot is None:
            raise MolqError("JOB_NOT_FOUND", f"job {job_id} not found on {target}")
        ref = dict(snapshot["ref"])
        offset = 0
        idle_for = 0.0
        while True:
            chunk, fresh = await asyncio.to_thread(_read_log, mq, ref, stream, offset)
            text = str(chunk.get("text") or "")
            offset = int(chunk.get("next_offset") or offset)
            if text:
                idle_for = 0.0
                for line in text.splitlines():
                    if line:
                        yield line
                continue
            snaps = fresh.get("snapshots") or []
            if snaps and snaps[0].get("terminal"):
                break
            if idle_for >= _LOG_IDLE_TIMEOUT_SECONDS:
                break
            await asyncio.sleep(_LOG_POLL_SECONDS)
            idle_for += _LOG_POLL_SECONDS
    finally:
        session.__exit__(None, None, None)

    yield "[stream closed]"


def _read_log(
    mq: _DashboardClient, ref: dict[str, str], stream: str, offset: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    job = mq.job(ref)
    return job.logs(stream=stream, offset=offset), job.status()


def _find_snapshot(mq: _DashboardClient, target: str, job_id: str) -> dict[str, Any] | None:
    snapshots = _queue_snapshots(mq, target)
    wanted_ref = _maybe_ref(job_id)
    for snapshot in snapshots:
        ref = snapshot.get("ref") or {}
        native = str(ref.get("native_id") or "")
        if native == job_id or (wanted_ref is not None and _ref_matches(ref, wanted_ref)):
            return snapshot
    return None


def _maybe_ref(job_id: str) -> dict[str, str] | None:
    from .submit import decode_job_ref

    return decode_job_ref(job_id)


def _ref_matches(left: dict[str, Any], right: dict[str, str]) -> bool:
    return all(str(left.get(key) or "") == right[key] for key in right)


def _to_summary(target: str, record: dict[str, Any], snapshot: dict[str, Any]) -> JobSummary:
    ref = snapshot.get("ref") or {}
    native = str(ref.get("native_id") or "")
    started = _to_datetime(snapshot.get("started_at"))
    finished = _to_datetime(snapshot.get("ended_at"))
    exit_code = snapshot.get("exit_code")
    return JobSummary(
        target=target,
        job_id=native,
        scheduler_job_id=native or None,
        cluster_name=str(record.get("id")) if record.get("id") else target,
        scheduler=str(record.get("scheduler")) if record.get("scheduler") else None,
        name=snapshot.get("name") if isinstance(snapshot.get("name"), str) else None,
        state=str(snapshot.get("state") or "unknown"),
        submitted_at=_to_datetime(snapshot.get("submitted_at")),
        started_at=started,
        finished_at=finished,
        exit_code=exit_code if isinstance(exit_code, int) else None,
        duration_seconds=_duration_seconds(started, finished),
        cwd=None,
    )


def _metadata(snapshot: dict[str, Any]) -> dict[str, str]:
    raw = snapshot.get("metadata")
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def _to_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _duration_seconds(started: datetime | None, finished: datetime | None) -> float | None:
    if started is None:
        return None
    end = finished or datetime.now(UTC)
    delta = (end - started).total_seconds()
    return delta if delta >= 0 else None


__all__ = [
    "JobDetail",
    "JobSummary",
    "JobTransition",
    "JobsPage",
    "QueueStats",
    "TargetSummary",
    "compute_stats",
    "fetch_page",
    "get_job",
    "list_jobs",
    "list_targets",
    "molq_session",
    "tail_log",
]
