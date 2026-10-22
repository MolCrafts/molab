"""``SubmitHandler.__call__`` — the molq submitter's attempt contract.

The handler asks the workspace for a QUEUED ``eNN`` record before any
transport or scheduler call, refuses an explicit id that is unknown or not
QUEUED, seals the attempt FAILED when something breaks before ``submit_job``
returns, and records the job ids on ``execution.json`` only (no ``job.json``).
``reconcile_submission`` is the level-triggered terminal check: it asks molq
for the job's current snapshot (``Job.status``) and seals a record the worker
never started once the job has ended. the application client is replaced by fakes
that record what they saw; no scheduler, SSH endpoint or worker process is
involved.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from molq import MolqError

from molab.plugins.submit_molq.submit import (
    SubmitHandler,
    encode_job_ref,
    make_submit_handler,
)
from molab.workspace import ComputeTarget, Workspace
from molab.workspace.domain import Execution, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.experiment import Experiment
from molab.workspace.project import Project
from molab.workspace.run import Run

type SubmitHook = Callable[[], None]


# ----------------------------------------------------------------------
# Fakes


@dataclass
class SubmitSpy:
    """What the fake molq session saw.

    ``record_at_submit`` is the Execution named by ``MOLAB_EXECUTION_ID``
    read inside ``submit``; ``record_error`` holds the lookup failure
    instead, so a missing record surfaces as an assertion, not a crash.
    """

    submits: int = 0
    argv: list[str] | None = None
    metadata: dict[str, str] | None = None
    record_at_submit: Execution | None = None
    record_error: str | None = None
    spec: Any = None


_FAKE_REF = {
    "registry_id": "reg",
    "cluster_id": "hpc",
    "native_id": "fake-sched-id",
    "incarnation": "1",
}
_JOB_ID = encode_job_ref(_FAKE_REF)


def _install_fake_submitor(
    monkeypatch: pytest.MonkeyPatch,
    run: Run,
    *,
    on_submit: SubmitHook | None = None,
    submit_error: Exception | None = None,
) -> SubmitSpy:
    """Replace the application client with a recording fake.

    Args:
        monkeypatch: The test's monkeypatch.
        run: The run whose record is captured at submit time.
        on_submit: Runs inside ``submit`` after the capture (a fast worker);
            a ``KeyError`` from it (no record to start) lands in ``record_error``.
        submit_error: Raised by ``submit`` after the capture.
    """
    spy = SubmitSpy()

    class _FakeJob:
        def __init__(self) -> None:
            self.ref = dict(_FAKE_REF)

    class _FakeCluster:
        def submit(
            self, spec: Any, *, argv: list[str] | None = None, request_key: str | None = None
        ) -> _FakeJob:
            del argv, request_key
            spy.submits += 1
            spy.spec = spec
            unit = spec.execution.units[0]
            command = unit.command
            spy.argv = list(command["argv"]) if command.get("kind") == "argv" else None
            spy.metadata = dict(spec.execution.env or {})
            execution_id = spy.metadata.get("MOLAB_EXECUTION_ID")
            try:
                spy.record_at_submit = run.execution(execution_id or "")
            except KeyError as exc:
                spy.record_error = f"no record for {execution_id!r}: {exc}"
            if submit_error is not None:
                raise submit_error
            if on_submit is not None:
                try:
                    on_submit()
                except KeyError as exc:
                    spy.record_error = f"fast worker found no record: {exc}"
            return _FakeJob()

    class _FakeMolq:
        def cluster(self, name: str) -> _FakeCluster:
            del name
            return _FakeCluster()

    def _session(_registry_id=None) -> _FakeMolq:
        return _FakeMolq()

    monkeypatch.setattr("molab.workspace.connection.get_client", _session)
    monkeypatch.setattr(
        "molab.workspace.targets.target_definition", lambda _t: {"id": "hpc", "scheduler": "slurm"}
    )
    return spy


@dataclass
class RecordingTransport:
    """A molq transport stand-in: records calls, never touches a host.

    ``upload_error`` makes ``upload`` raise; ``texts`` serves ``read_text``
    by path suffix, otherwise ``read_text`` raises ``TransportError``.
    """

    upload_error: Exception | None = None
    texts: dict[str, str] = field(default_factory=dict)
    uploads: list[tuple[str, str]] = field(default_factory=list)
    downloads: list[tuple[str, str]] = field(default_factory=list)
    mkdirs: list[str] = field(default_factory=list)

    def read_text(self, path: str) -> str:
        for suffix, text in self.texts.items():
            if path.endswith(suffix):
                return text
        raise OSError("no such remote file")

    def read_bytes(self, path: str) -> bytes:
        return self.read_text(path).encode()

    def write_text(self, path: str, data: str, *, mode: int = 0o600) -> None:
        del path, data, mode

    def write_bytes(self, path: str, data: bytes, *, mode: int = 0o600) -> None:
        del path, data, mode

    def exists(self, path: str) -> bool:
        return any(path.endswith(suffix) for suffix in self.texts)

    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> None:
        del parents, exist_ok
        self.mkdirs.append(path)

    def chmod(self, path: str, mode: int) -> None:
        del path, mode

    def remove(self, path: str, *, recursive: bool = False) -> None:
        del path, recursive

    def upload(
        self, local: str, remote: str, *, recursive: bool = False, exclude: tuple[str, ...] = ()
    ) -> None:
        del recursive, exclude
        if self.upload_error is not None:
            raise self.upload_error
        self.uploads.append((local, remote))

    def download(
        self, remote: str, local: str, *, recursive: bool = False, exclude: tuple[str, ...] = ()
    ) -> None:
        del recursive, exclude
        self.downloads.append((remote, local))


# ----------------------------------------------------------------------
# Helpers


def _make_run(tmp_path: Path) -> tuple[Workspace, Project, Experiment, Run]:
    ws = Workspace(tmp_path)
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e", params={})
    run = experiment.add_run(params={"seed": 1})
    return ws, project, experiment, run


def _remote_target() -> ComputeTarget:
    return ComputeTarget(
        name="hpc",
        registry_id="reg",
        cluster_id="hpc",
        scratch_root="/scratch/me/molab",
    )


def _handler(target: ComputeTarget | None = None) -> SubmitHandler:
    return make_submit_handler(
        scheduler="local",
        cluster="local",
        resources={},
        scheduling={},
        target=target,
    )


def _repository(ws: Workspace, project: Project, run: Run) -> ExecutionRepository:
    return ExecutionRepository(ws.root, run.run_dir, run_id=run.id, project_id=project.id, fs=ws.fs)


def _execution_ids(run: Run) -> list[str]:
    executions = Path(run.run_dir) / "executions"
    if not executions.is_dir():
        return []
    return sorted(p.name for p in executions.iterdir())


def _record_bytes(run: Run, execution_id: str) -> bytes:
    return (Path(run.run_dir) / "executions" / execution_id / "execution.json").read_bytes()


def _submitted_record(spy: SubmitSpy) -> Execution:
    """The record ``submit_job`` saw, or an assertion naming why there was none."""
    assert spy.submits == 1
    assert spy.record_error is None, spy.record_error
    assert spy.record_at_submit is not None
    return spy.record_at_submit


# ----------------------------------------------------------------------
# SubmitHandler.__call__


class TestSubmitHandler:
    def test_creates_queued_record_before_submit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        monkeypatch.chdir(tmp_path)
        spy = _install_fake_submitor(monkeypatch, run)

        _handler()(None, run, experiment, project)

        record = _submitted_record(spy)
        assert record.id == "e01"
        assert record.status.value == "queued"
        assert record.mode.value == "initial"
        assert record.executor == {"backend": "molq", "target": None}
        assert record.environment.get("submit_cwd") == str(tmp_path.resolve())
        assert spy.metadata is not None
        assert spy.metadata["MOLAB_EXECUTION_ID"] == "e01"
        assert spy.argv is not None
        flag = spy.argv.index("--execution-id")
        assert spy.argv[flag : flag + 2] == ["--execution-id", "e01"]

    def test_the_worker_interpreter_is_configurable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """An x86 login node submitting to aarch64 GPUs names the node's python."""
        _ws, project, experiment, run = _make_run(tmp_path)
        spy = _install_fake_submitor(monkeypatch, run)
        handler = make_submit_handler(
            scheduler="local",
            cluster="local",
            resources={},
            scheduling={},
            python="/venvs/aarch64/bin/python",
        )

        handler(None, run, experiment, project)

        assert spy.argv is not None
        assert spy.argv[0] == "/venvs/aarch64/bin/python"

    def test_no_uuid_execution_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        _install_fake_submitor(monkeypatch, run)

        _handler()(None, run, experiment, project)

        assert _execution_ids(run) == ["e01"]

    def test_records_job_on_the_record_without_sidecar(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        _install_fake_submitor(monkeypatch, run)

        _handler()(None, run, experiment, project)

        executor = run.execution("e01").executor
        assert executor["job_id"] == _JOB_ID
        assert executor["backend"] == "molq"
        assert executor["scheduler"] == "local"
        assert not (Path(run.run_dir) / "executions" / "e01" / "job.json").exists()

    def test_second_submit_after_terminal_is_rerun(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        run._create_execution()
        run.cancel("e01")
        spy = _install_fake_submitor(monkeypatch, run)

        _handler()(None, run, experiment, project)

        record = _submitted_record(spy)
        assert record.id == "e02"
        assert record.mode.value == "rerun"
        assert record.based_on_execution_id == "e01"
        assert record.status.value == "queued"

    def test_explicit_non_queued_id_raises_before_submit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        run._create_execution()
        run.cancel("e01")
        spy = _install_fake_submitor(monkeypatch, run)

        with pytest.raises(ValueError):
            _handler()(None, run, experiment, project, execution_id="e01")

        assert spy.submits == 0
        assert _execution_ids(run) == ["e01"]

    def test_explicit_unknown_id_raises_before_submit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        spy = _install_fake_submitor(monkeypatch, run)

        with pytest.raises(KeyError):
            _handler()(None, run, experiment, project, execution_id="e09")

        assert spy.submits == 0
        assert not (Path(run.run_dir) / "executions" / "e09").exists()
        assert run.executions == []

    def test_active_predecessor_raises_before_submit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        run._create_execution()
        spy = _install_fake_submitor(monkeypatch, run)

        with pytest.raises(ValueError):
            _handler()(None, run, experiment, project)

        assert spy.submits == 0
        assert _execution_ids(run) == ["e01"]

    def test_submit_error_seals_failed_and_reraises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ws, project, experiment, run = _make_run(tmp_path)
        _install_fake_submitor(monkeypatch, run, submit_error=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            _handler()(None, run, experiment, project)

        e01 = run.execution("e01")
        assert e01.status.value == "failed"
        assert e01.sealed_at is not None
        assert e01.error == {"type": "RuntimeError", "message": "boom"}
        again = _repository(ws, project, run).seal(
            "e01", ExecutionStatus.FAILED, error={"type": "RuntimeError", "message": "boom"}
        )
        assert again.sealed_at == e01.sealed_at

    def test_stage_in_failure_seals_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        transport = RecordingTransport(upload_error=OSError("down"))
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: transport)
        spy = _install_fake_submitor(monkeypatch, run)

        with pytest.raises(OSError):
            _handler(_remote_target())(None, run, experiment, project)

        e01 = run.execution("e01")
        assert e01.status.value == "failed"
        assert e01.error is not None
        assert e01.error["type"] == "OSError"
        assert spy.submits == 0

    def test_error_after_submit_does_not_seal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        _install_fake_submitor(monkeypatch, run)

        def fail_update(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("late")

        monkeypatch.setattr(ExecutionRepository, "update_operational", fail_update)

        with pytest.raises(RuntimeError, match="late"):
            _handler()(None, run, experiment, project)

        e01 = run.execution("e01")
        assert e01.status.value == "queued"
        assert e01.sealed_at is None

    def test_fast_worker_keys_survive_submission(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        ws, project, experiment, run = _make_run(tmp_path)

        def worker_starts() -> None:
            _repository(ws, project, run).start(
                "e01", executor={"kind": "local", "host": "h", "pid": 9}
            )

        spy = _install_fake_submitor(monkeypatch, run, on_submit=worker_starts)

        _handler()(None, run, experiment, project)

        _submitted_record(spy)
        executor = run.execution("e01").executor
        assert executor["kind"] == "local"
        assert executor["host"] == "h"
        assert executor["pid"] == 9
        assert executor["backend"] == "molq"
        assert "target" in executor
        assert executor["target"] is None
        assert executor["job_id"] == _JOB_ID
        assert executor["scheduler_job_id"] == "fake-sched-id"

    def test_fast_worker_sealed_before_submit_returns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        ws, project, experiment, run = _make_run(tmp_path)

        def worker_starts_and_seals() -> None:
            repo = _repository(ws, project, run)
            repo.start("e01", executor={"kind": "local", "host": "h", "pid": 9})
            repo.seal("e01", ExecutionStatus.SUCCEEDED)

        spy = _install_fake_submitor(monkeypatch, run, on_submit=worker_starts_and_seals)
        handler = _handler()

        handler(None, run, experiment, project)

        _submitted_record(spy)
        assert run in handler.submitted_runs
        e01 = run.execution("e01")
        assert e01.status.value == "succeeded"
        assert e01.executor["kind"] == "local"
        assert e01.executor["host"] == "h"
        assert e01.executor["pid"] == 9
        assert "job_id" not in e01.executor
        err = capsys.readouterr().err
        assert "job fake-sched-id submitted for run" in err
        assert "attempt e01" in err
        assert "already succeeded" in err

    def test_interrupt_before_submit_returns_seals_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)

        def interrupted() -> None:
            raise KeyboardInterrupt

        _install_fake_submitor(monkeypatch, run, on_submit=interrupted)

        with pytest.raises(KeyboardInterrupt):
            _handler()(None, run, experiment, project)

        e01 = run.execution("e01")
        assert e01.status.value == "failed"
        assert e01.sealed_at is not None
        assert e01.error is not None
        assert e01.error["type"] == "KeyboardInterrupt"


# ----------------------------------------------------------------------
# reconcile_submission — level-triggered terminal handling (spec §1e-prime)


_TERMINAL = frozenset({"failed", "succeeded", "cancelled", "timed_out"})
_TERMINAL_TO_STATUS = [
    ("failed", "failed"),
    ("succeeded", "failed"),
    ("cancelled", "cancelled"),
    ("timed_out", "failed"),
]


@dataclass
class RefreshSpy:
    """Job refs ``Job.status`` was asked about."""

    queried: list[str] = field(default_factory=list)


def _install_refreshing_submitor(
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: str = "queued",
    refresh_error: Exception | None = None,
) -> RefreshSpy:
    """Replace the application client with a fake whose ``status`` reports *state*."""
    spy = RefreshSpy()

    class _Job:
        def __init__(self, ref: dict[str, str]) -> None:
            self.ref = ref

        def status(self, **_kw: object) -> dict[str, object]:
            if refresh_error is not None:
                raise refresh_error
            spy.queried.append(encode_job_ref(self.ref))
            return {
                "snapshots": [{"ref": self.ref, "state": state, "terminal": state in _TERMINAL}]
            }

    class _Molq:
        def job(self, ref: dict[str, str]) -> _Job:
            return _Job(ref)

    def _session(_registry_id=None) -> _Molq:
        return _Molq()

    monkeypatch.setattr("molab.workspace.connection.get_client", _session)
    monkeypatch.setattr(
        "molab.workspace.targets.target_definition", lambda _t: {"id": "hpc", "scheduler": "slurm"}
    )
    return spy


def _submit_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Workspace, Project, Run]:
    """Submit e01 through the real handler (local target) and return the run."""
    ws, project, experiment, run = _make_run(tmp_path)
    spy = _install_fake_submitor(monkeypatch, run)
    _handler()(None, run, experiment, project)
    assert _submitted_record(spy).id == "e01"
    assert run.execution("e01").executor["job_id"] == _JOB_ID
    return ws, project, run


def _submit_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Run, RecordingTransport]:
    """Submit e01 to the registered remote target ``hpc`` and return the run."""
    ws, project, experiment, run = _make_run(tmp_path)
    target = _remote_target()
    ws.add_target(target)
    transport = RecordingTransport()
    monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: transport)
    spy = _install_fake_submitor(monkeypatch, run)
    _handler(target)(None, run, experiment, project)
    assert _submitted_record(spy).id == "e01"
    assert run.execution("e01").executor["target"] == "hpc"
    return run, transport


class TestReconcileSubmission:
    @pytest.mark.parametrize(("state", "expected"), _TERMINAL_TO_STATUS)
    def test_terminal_job_seals_unstarted_record(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        state: str,
        expected: str,
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        spy = _install_refreshing_submitor(monkeypatch, state=state)

        returned = reconcile_submission(run, "e01")

        assert spy.queried == [_JOB_ID]
        e01 = run.execution("e01")
        assert e01.status.value == expected
        assert e01.sealed_at is not None
        assert e01.error is not None
        assert e01.error["type"] == "SchedulerJobEndedBeforeStart"
        assert state in str(e01.error["message"]).lower()
        assert returned.record == e01
        assert returned.error is None

    def test_rebuilds_submitor_from_recorded_executor(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        executor = run.execution("e01").executor
        spy = _install_refreshing_submitor(monkeypatch, state="running")

        reconcile_submission(run, "e01")

        assert spy.queried == [executor["job_id"]]

    @pytest.mark.parametrize("state", ["running", "queued"])
    def test_non_terminal_job_leaves_record_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, state: str
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        before = _record_bytes(run, "e01")
        spy = _install_refreshing_submitor(monkeypatch, state=state)

        returned = reconcile_submission(run, "e01")

        assert spy.queried == [_JOB_ID]
        assert _record_bytes(run, "e01") == before
        assert returned.record.status.value == "queued"
        assert returned.record.sealed_at is None
        assert returned.error is None

    def test_running_record_is_left_to_the_reaper(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        ws, project, run = _submit_local(monkeypatch, tmp_path)
        _repository(ws, project, run).start("e01")
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        returned = reconcile_submission(run, "e01")

        assert spy.queried == []
        e01 = run.execution("e01")
        assert e01.status.value == "running"
        assert e01.sealed_at is None
        assert returned.record.status.value == "running"
        assert returned.error is None

    def test_sealed_record_returned_without_querying_molq(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        run.cancel("e01")
        before = _record_bytes(run, "e01")
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        returned = reconcile_submission(run, "e01")

        assert spy.queried == []
        assert _record_bytes(run, "e01") == before
        assert returned.record == run.execution("e01")
        assert returned.error is None
        assert returned.record.status.value == "cancelled"

    def test_non_molq_record_returned_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, _experiment, run = _make_run(tmp_path)
        run._create_execution()
        before = _record_bytes(run, "e01")
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        returned = reconcile_submission(run, "e01")

        assert spy.queried == []
        assert _record_bytes(run, "e01") == before
        assert returned.record.status.value == "queued"
        assert returned.error is None

    def test_molq_record_without_job_id_returned_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, _experiment, run = _make_run(tmp_path)
        run._create_execution(executor={"backend": "molq", "target": None})
        before = _record_bytes(run, "e01")
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        returned = reconcile_submission(run, "e01")

        assert spy.queried == []
        assert _record_bytes(run, "e01") == before
        assert returned.record.status.value == "queued"
        assert returned.error is None

    def test_repeated_reconcile_is_idempotent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        first = reconcile_submission(run, "e01")
        after_first = _record_bytes(run, "e01")
        second = reconcile_submission(run, "e01")

        assert first.record.sealed_at is not None
        assert second.record.sealed_at == first.record.sealed_at
        assert first.error is None
        assert second.error is None
        assert _record_bytes(run, "e01") == after_first
        assert spy.queried == [_JOB_ID]

    def test_remote_unreadable_record_stays_queued(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        run, transport = _submit_remote(monkeypatch, tmp_path)
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        returned = reconcile_submission(run, "e01")

        assert spy.queried == [_JOB_ID]
        assert transport.downloads, "a terminal remote job still stages out"
        e01 = run.execution("e01")
        assert e01.status.value == "queued"
        assert e01.sealed_at is None
        assert returned.record.status.value == "queued"
        assert returned.error is None

    def test_remote_queued_record_sealed_after_merge(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        run, transport = _submit_remote(monkeypatch, tmp_path)
        transport.texts["/executions/e01/execution.json"] = json.dumps(
            {"schema_version": 4, **run.execution("e01").model_dump(mode="json")}
        )
        _install_refreshing_submitor(monkeypatch, state="failed")

        returned = reconcile_submission(run, "e01")

        e01 = run.execution("e01")
        assert e01.status.value == "failed"
        assert e01.error is not None
        assert e01.error["type"] == "SchedulerJobEndedBeforeStart"
        assert e01.executor["job_id"] == _JOB_ID
        assert returned.record == e01
        assert returned.error is None

    @pytest.mark.parametrize(
        "refresh_error",
        [
            OSError("scheduler unreachable"),
            MolqError("JOB_NOT_FOUND", "missing"),
        ],
        ids=["transport-error", "job-not-found"],
    )
    def test_refresh_failure_reported_and_record_left_alone(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        refresh_error: Exception,
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        before = _record_bytes(run, "e01")
        _install_refreshing_submitor(monkeypatch, refresh_error=refresh_error)
        capsys.readouterr()

        returned = reconcile_submission(run, "e01")

        assert capsys.readouterr().err == ""
        assert returned.error == (
            f"could not reconcile run {run.id} attempt e01: "
            f"{type(refresh_error).__name__}: {refresh_error}"
        )
        assert _record_bytes(run, "e01") == before
        assert returned.record.status.value == "queued"


class TestReconcileOutcome:
    """``reconcile_submission`` reports through its return value, QUEUED only.

    The monitor that calls it runs inside a full-screen terminal view, where
    stderr is overwritten; a failure therefore comes back as
    ``ReconcileOutcome.error`` and nothing is printed. Only a QUEUED record
    can be sealed, so nothing else reaches molq.
    """

    def test_running_record_does_not_query_molq(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        ws, project, run = _submit_local(monkeypatch, tmp_path)
        _repository(ws, project, run).start("e01")
        before = _record_bytes(run, "e01")
        spy = _install_refreshing_submitor(monkeypatch, state="failed")

        outcome = reconcile_submission(run, "e01")

        assert spy.queried == []
        assert _record_bytes(run, "e01") == before
        assert outcome.record == run.execution("e01")
        assert outcome.record.status.value == "running"
        assert outcome.error is None

    def test_sealing_outcome_carries_record_and_no_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        _install_refreshing_submitor(monkeypatch, state="failed")

        outcome = reconcile_submission(run, "e01")

        assert outcome.error is None
        assert outcome.record == run.execution("e01")
        assert outcome.record.status.value == "failed"

    @pytest.mark.parametrize(
        "refresh_error",
        [
            OSError("scheduler unreachable"),
            MolqError("JOB_NOT_FOUND", "missing"),
        ],
        ids=["transport-error", "job-not-found"],
    )
    def test_expected_failure_returned_as_error_not_printed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        refresh_error: Exception,
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        before = _record_bytes(run, "e01")
        _install_refreshing_submitor(monkeypatch, refresh_error=refresh_error)
        capsys.readouterr()

        outcome = reconcile_submission(run, "e01")

        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""
        assert outcome.error == (
            f"could not reconcile run {run.id} attempt e01: "
            f"{type(refresh_error).__name__}: {refresh_error}"
        )
        assert _record_bytes(run, "e01") == before
        assert outcome.record.status.value == "queued"

    def test_programming_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.plugins.submit_molq.submit import reconcile_submission

        _ws, _project, run = _submit_local(monkeypatch, tmp_path)
        _install_refreshing_submitor(monkeypatch, refresh_error=TypeError("a bug"))

        with pytest.raises(TypeError, match="a bug"):
            reconcile_submission(run, "e01")


def test_unknown_submission_is_not_sealed_or_automatically_repeated(monkeypatch, tmp_path):
    from molq import MolqError

    _, project, experiment, run = _make_run(tmp_path)
    spy = _install_fake_submitor(
        monkeypatch,
        run,
        submit_error=MolqError("OUTCOME_UNKNOWN", "Lost response", outcome="unknown"),
    )
    with pytest.raises(MolqError):
        _handler()(None, run, experiment, project)
    assert spy.submits == 1
    record = run.execution("e01")
    assert record.status.value == "queued" and record.executor["submission_outcome"] == "unknown"


def test_reconcile_uses_the_recorded_destination_and_stops_after_uncertain_transfer(
    monkeypatch, tmp_path
):
    from molq import MolqError

    from molab.plugins.submit_molq.submit import reconcile_submission

    run, transport = _submit_remote(monkeypatch, tmp_path)
    ws = run.experiment.project.workspace
    ws.remove_target("hpc")
    _install_refreshing_submitor(monkeypatch, state="succeeded")
    seen = []

    def uncertain_download(*args: object, **_kwargs: object):
        seen.append(args)
        raise MolqError("OUTCOME_UNKNOWN", "Lost transfer response", outcome="unknown")

    transport.download = uncertain_download
    first = reconcile_submission(run, "e01")
    second = reconcile_submission(run, "e01")
    assert first.error and second.error and len(seen) == 1
    assert run.execution("e01").executor["transfer_outcome"] == "unknown"
