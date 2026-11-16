"""Public-API goldens for arch-own-02d-submit.

The molq submitter no longer mints execution ids or writes sidecars; the
workspace allocates every attempt and ``execution.json`` is its one record:

1. ``make_submit_handler(target=hpc)`` called with no id creates a QUEUED
   ``e01`` (mode ``initial``) through ``Run.create_execution`` *before*
   ``submit_job`` runs — the stubbed ``Submitor`` sees it on disk.
2. Remote stage-in uploads the run dir (without ``executions/``) and then the
   one attempt's ``executions/e01`` directory, so the remote worker finds its
   QUEUED record.
3. The job ids land in ``e01``'s ``executor``; ``executions/e01/job.json`` is
   no longer written.
4. ``stage_out`` reads the worker's remote ``execution.json`` (sealed
   ``succeeded``, ``host=node7``) and merges it: the worker's status and host
   win, the local job id survives.
5. Submitting the sealed ``e01`` again by id raises ``ValueError`` before any
   scheduler call (the submit count stays 1).
6. A second submit with no id creates ``e02`` as a ``rerun`` based on ``e01``.

Expected stdout (exactly these lines, exit code 0):

    submit-time: e01 queued initial
    staged: executions/e01
    recorded: e01 fake-job-1 slurm job.json=absent
    merged: e01 succeeded job=fake-job-1 host=node7
    rejected: ValueError submits=1
    rerun: e02 queued rerun e01
    arch-own-02d-submit: ok

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. ``molq`` is a
molab dependency, not an oracle: ``molq.Submitor`` and
``molab.workspace.targets.to_transport`` are replaced by in-script stubs
(restored in ``finally``), so no scheduler, SSH connection or subprocess is
contacted. The workspace is an in-process temporary directory.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

import molq

import molab.workspace.targets as targets_module
from molab.plugins.submit_molq.staging import stage_out
from molab.plugins.submit_molq.submit import make_submit_handler
from molab.workspace import ComputeTarget, Workspace
from molab.workspace.domain import Execution
from molab.workspace.run import Run

_GOLDEN = (
    "submit-time: e01 queued initial",
    "staged: executions/e01",
    "recorded: e01 fake-job-1 slurm job.json=absent",
    "merged: e01 succeeded job=fake-job-1 host=node7",
    "rejected: ValueError submits=1",
    "rerun: e02 queued rerun e01",
)


def _emit(lines: list[str], line: str) -> None:
    expected = _GOLDEN[len(lines)]
    assert line == expected, f"{line!r} != {expected!r}"
    lines.append(line)
    print(line)


@dataclass
class _RecordingTransport:
    """Records uploads; ``download`` is a no-op; ``read_text`` serves ``files``."""

    uploads: list[tuple[str, str]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)

    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> None:  # noqa: ARG002
        return None

    def upload(
        self,
        local: str,
        remote: str,
        *,
        recursive: bool = False,  # noqa: ARG002
        exclude: tuple[str, ...] = (),
    ) -> None:
        print(f"upload {local} -> {remote} exclude={list(exclude)}", file=sys.stderr)
        self.uploads.append((local, remote))

    def download(
        self,
        remote: str,
        local: str,
        *,
        recursive: bool = False,  # noqa: ARG002
        exclude: tuple[str, ...] = (),
    ) -> None:
        print(f"download {remote} -> {local} exclude={list(exclude)}", file=sys.stderr)

    def read_text(self, path: str) -> str:
        return self.files[path]


class _FakeJob:
    def __init__(self, n: int) -> None:
        self.job_id = f"fake-job-{n}"
        self.scheduler_job_id = f"fake-sched-{n}"


class _EventBus:
    def on(self, *_args: object, **_kwargs: object) -> None:
        return None


def _make_submitor(run: Run, seen: list[Execution]) -> type:
    """A ``molq.Submitor`` stand-in recording ``run.executions[-1]`` per submit."""

    class _FakeSubmitor:
        def __init__(self, target: object, *, jobs_dir: str) -> None:  # noqa: ARG002
            self._event_bus = _EventBus()

        def __enter__(self) -> _FakeSubmitor:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            return False

        def submit_job(self, **kwargs: object) -> _FakeJob:
            print(f"submit_job metadata={kwargs.get('metadata')}", file=sys.stderr)
            seen.append(run.executions[-1])
            return _FakeJob(len(seen))

    return _FakeSubmitor


def _check(raw: Path) -> None:
    lines: list[str] = []
    ws = Workspace(root=raw / "lab", name="Lab")
    run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    run_dir = Path(run.run_dir).resolve()
    target = ComputeTarget(
        name="hpc", host="me@cluster", scheduler="slurm", scratch_root="/scratch/me/molab"
    )
    transport = _RecordingTransport()
    seen: list[Execution] = []

    saved_submitor = molq.Submitor
    saved_to_transport = targets_module.to_transport
    molq.Submitor = _make_submitor(run, seen)  # type: ignore[misc]
    targets_module.to_transport = lambda _t: transport  # type: ignore[assignment]
    try:
        handler = make_submit_handler(
            scheduler="ignored", cluster=None, resources={}, scheduling={}, target=target
        )
        project = run.experiment.project
        experiment = run.experiment

        # 1-2. Submit with no id: the QUEUED e01 exists before submit_job.
        handler(None, run, experiment, project)
        first = seen[0]
        _emit(lines, f"submit-time: {first.id} {first.status.value} {first.mode.value}")

        # 3. The second upload carries the attempt directory.
        exec_local, exec_remote = transport.uploads[1]
        staged = Path(exec_local).resolve().relative_to(run_dir).as_posix()
        _emit(lines, f"staged: {staged}")

        # 4. Job ids live in execution.json only.
        e01 = run.execution("e01")
        job_json = (run_dir / "executions" / "e01" / "job.json").exists()
        _emit(
            lines,
            f"recorded: {e01.id} {e01.executor.get('job_id')} {e01.executor.get('scheduler')} "
            f"job.json={'present' if job_json else 'absent'}",
        )

        # 5. The worker's sealed remote record merges in; the local job id survives.
        document = e01.model_dump(mode="json")
        document.update(
            status="succeeded",
            started_at="2026-09-26T10:00:00Z",
            finished_at="2026-09-26T10:05:00Z",
            sealed_at="2026-09-26T10:05:01Z",
            executor={
                "backend": "molq",
                "target": "hpc",
                "kind": "local",
                "host": "node7",
                "pid": 4242,
            },
        )
        transport.files[f"{exec_remote}/execution.json"] = json.dumps(document)
        pulled = stage_out(transport, run, target, "e01")  # type: ignore[arg-type]
        assert pulled, "stage_out did not merge the remote record"
        merged = run.execution("e01")
        print(f"merged executor: {merged.executor}", file=sys.stderr)
        _emit(
            lines,
            f"merged: {merged.id} {merged.status.value} job={merged.executor.get('job_id')} "
            f"host={merged.executor.get('host')}",
        )

        # 6. A sealed attempt cannot be submitted again by id.
        try:
            handler(None, run, experiment, project, execution_id="e01")
        except ValueError as exc:
            print(f"rejected: {exc}", file=sys.stderr)
            _emit(lines, f"rejected: {type(exc).__name__} submits={len(seen)}")
        else:
            raise AssertionError("submitting the sealed e01 did not raise ValueError")

        # 7. A new submit allocates e02 as a rerun of e01.
        handler(None, run, experiment, project)
        second = seen[-1]
        _emit(
            lines,
            f"rerun: {second.id} {second.status.value} {second.mode.value} "
            f"{second.based_on_execution_id}",
        )
    finally:
        molq.Submitor = saved_submitor  # type: ignore[misc]
        targets_module.to_transport = saved_to_transport

    assert len(lines) == len(_GOLDEN), lines
    print("arch-own-02d-submit: ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        os.environ["GIT_CEILING_DIRECTORIES"] = raw
        _check(Path(raw))


if __name__ == "__main__":
    main()
