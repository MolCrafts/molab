"""SubmitHandler must route through the target's transport when one is set.

Uses a fake transport that records every shell call + file op, plus a fake
molq ``Submitor`` so we don't need a working SSH endpoint or a real worker
subprocess.  The assertions cover the wiring — with-target vs no-target — not
the worker behaviour, which is exercised by the molq suite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest
from molq.transport import CommandResult

from molab.workspace import AgentRef, ComputeTarget, Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_repository import ExecutionRepository


@dataclass
class RecordingTransport:
    """A transport that no-ops every method but records the calls.

    ``upload`` / ``download`` also record their ``exclude`` patterns so a test
    can decide which local files a staging transfer actually carries.
    """

    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    def _record(self, method: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((method, args, kwargs))

    def run(self, argv, *, cwd=None, env=None, input=None, timeout=None):
        self._record("run", (tuple(argv),), {"cwd": cwd, "env": env, "input": input})
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    def read_text(self, path: str) -> str:
        return ""

    def read_bytes(self, path: str) -> bytes:
        return b""

    def write_text(self, path: str, data: str, *, mode: int = 0o600) -> None:
        self._record("write_text", (path,), {"mode": mode})

    def write_bytes(self, path: str, data: bytes, *, mode: int = 0o600) -> None:
        self._record("write_bytes", (path,), {"mode": mode})

    def exists(self, path: str) -> bool:
        return True

    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> None:
        self._record("mkdir", (path,), {})

    def chmod(self, path: str, mode: int) -> None:
        return None

    def remove(self, path: str, *, recursive: bool = False) -> None:
        return None

    def upload(self, local: str, remote: str, *, recursive: bool = False, exclude=()) -> None:
        self._record("upload", (local, remote), {"recursive": recursive, "exclude": tuple(exclude)})

    def download(self, remote: str, local: str, *, recursive: bool = False, exclude=()) -> None:
        self._record(
            "download", (remote, local), {"recursive": recursive, "exclude": tuple(exclude)}
        )


def _uploads_cover(calls: list[tuple[str, tuple, dict]], local_file: Path) -> bool:
    """True iff one recorded ``upload`` carries *local_file* to the remote side.

    An upload covers the file when its ``local`` source is the file itself or
    one of its ancestors, and no component of the file's path relative to that
    source matches any of the upload's ``exclude`` patterns.
    """
    target = Path(local_file).resolve()
    for method, args, kwargs in calls:
        if method != "upload":
            continue
        source = Path(args[0]).resolve()
        if target != source and source not in target.parents:
            continue
        parts = target.relative_to(source).parts
        patterns = kwargs.get("exclude", ())
        if not any(fnmatch(part, pattern) for part in parts for pattern in patterns):
            return True
    return False


def _make_run(tmp_path: Path):
    ws = Workspace(tmp_path)
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e", params={})
    run = experiment.add_run(params={"seed": 1})
    return ws, project, experiment, run


def _remote_target() -> ComputeTarget:
    return ComputeTarget(
        name="hpc",
        host="me@cluster",
        scheduler="slurm",
        scratch_root="/scratch/me/molab",
    )


def _remote_handler():
    from molab.plugins.submit_molq.submit import make_submit_handler

    return make_submit_handler(
        scheduler="ignored-when-target-set",
        cluster=None,
        resources={},
        scheduling={},
        target=_remote_target(),
    )


def _precreate_e01(ws: Workspace, project, run) -> None:
    """Allocate the QUEUED ``e01`` the way the server does before dispatch."""
    ExecutionRepository(
        ws.root, run.run_dir, run_id=run.id, project_id=project.id, fs=ws.fs
    ).create(
        mode=ExecutionMode.INITIAL,
        created_by=AgentRef(id="test", type="person", name="test"),
    )


def _install_fake_submitor(monkeypatch: pytest.MonkeyPatch, run) -> dict[str, Any]:
    """Replace ``molq.Submitor``; record what ``submit_job`` saw.

    ``records_at_submit`` snapshots ``(id, status)`` of every Execution on disk
    at the moment ``submit_job`` is called.
    """
    captured: dict[str, Any] = {}

    class FakeJob:
        job_id = "fake-job-id"
        scheduler_job_id = "fake-sched-id"

    class FakeSubmitor:
        def __init__(self, target, *, jobs_dir):
            captured["scheduler"] = target.scheduler
            captured["jobs_dir"] = jobs_dir
            self._event_bus = type("EB", (), {"on": lambda *_a, **_kw: None})()

        def __enter__(self):
            return self

        def __exit__(self, *a):  # noqa: ANN002
            return False

        def submit_job(self, *, argv, resources, scheduling, execution, metadata):
            captured["submit_argv"] = argv
            captured["submit_cwd"] = execution.cwd
            captured["submit_metadata"] = metadata
            captured["records_at_submit"] = [(e.id, e.status.value) for e in run.executions]
            return FakeJob()

    monkeypatch.setattr("molq.Submitor", FakeSubmitor)
    return captured


class TestSubmitHandler:
    def test_with_target_stages_in_and_routes_through_transport(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        target = ComputeTarget(
            name="hpc",
            host="me@cluster",
            scheduler="slurm",
            scratch_root="/scratch/me/molab",
        )

        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_transport", lambda _t: transport)

        captured_submitor: dict[str, Any] = {}

        class FakeJob:
            job_id = "fake-job-id"
            scheduler_job_id = "fake-sched-id"

        class FakeSubmitor:
            def __init__(self, target, *, jobs_dir):
                captured_submitor["cluster_name"] = target.name
                captured_submitor["scheduler"] = target.scheduler
                captured_submitor["jobs_dir"] = jobs_dir
                captured_submitor["transport"] = target.transport
                self._event_bus = type("EB", (), {"on": lambda *_a, **_kw: None})()

            def __enter__(self):
                return self

            def __exit__(self, *a):  # noqa: ANN002
                return False

            def submit_job(self, *, argv, resources, scheduling, execution, metadata):
                captured_submitor["submit_argv"] = argv
                captured_submitor["submit_cwd"] = execution.cwd
                captured_submitor["submit_metadata"] = metadata
                return FakeJob()

        # Submitor is imported lazily from ``molq`` inside __call__.
        monkeypatch.setattr("molq.Submitor", FakeSubmitor)

        from molab.plugins.submit_molq.submit import make_submit_handler

        handler = make_submit_handler(
            scheduler="ignored-when-target-set",
            cluster=None,
            resources={},
            scheduling={},
            target=target,
        )
        handler(None, run, experiment, project)

        # Stage-in happened: the run dir, then the one attempt's directory.
        uploads = [c for c in transport.calls if c[0] == "upload"]
        assert len(uploads) == 2
        src, dst = uploads[0][1]
        assert src == str(Path(run.run_dir).resolve())
        assert dst.startswith("/scratch/me/molab/")
        exec_src, exec_dst = uploads[1][1]
        assert exec_src.endswith("/executions/e01")
        assert exec_dst.startswith("/scratch/me/molab/")
        assert exec_dst.endswith("/executions/e01")

        # Submitor was constructed with the target's scheduler + transport.
        assert captured_submitor["scheduler"] == "slurm"
        assert captured_submitor["transport"] is transport
        # The worker is told to chdir into the remote exec dir.
        assert captured_submitor["submit_cwd"].startswith("/scratch/me/molab/")
        assert "executions/" in captured_submitor["submit_cwd"]
        # Argv points at the remote run dir, not the local one.
        argv = captured_submitor["submit_argv"]
        assert "molab.cli" in argv and "execute" in argv
        assert any(a.startswith("/scratch/me/molab/") for a in argv)

    def test_without_target_falls_back_to_local_transport(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """No-target path: transport=None on the handler → Cluster falls back
        to ``LocalTransport`` and no staging happens."""
        _, project, experiment, run = _make_run(tmp_path)

        captured: dict[str, Any] = {}

        class FakeJob:
            job_id = "x"
            scheduler_job_id = "y"

        class FakeSubmitor:
            def __init__(self, target, *, jobs_dir):
                captured["transport"] = target.transport
                captured["jobs_dir"] = jobs_dir
                self._event_bus = type("EB", (), {"on": lambda *_a, **_kw: None})()

            def __enter__(self):
                return self

            def __exit__(self, *a):  # noqa: ANN002
                return False

            def submit_job(self, *, argv, resources, scheduling, execution, metadata):
                captured["cwd"] = execution.cwd
                return FakeJob()

        monkeypatch.setattr("molq.Submitor", FakeSubmitor)

        from molab.plugins.submit_molq.submit import make_submit_handler

        handler = make_submit_handler(
            scheduler="local",
            cluster=None,
            resources={},
            scheduling={},
            target=None,
        )
        handler(None, run, experiment, project)

        # No target → Cluster gets transport=None and falls back to LocalTransport.
        from molq.transport import LocalTransport

        assert isinstance(captured["transport"], LocalTransport)
        # jobs_dir lives under the LOCAL run dir, not a remote scratch path.
        assert captured["jobs_dir"].startswith(str(run.run_dir))

    def test_precreated_execution_id_is_submitted_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The server path precreates ``e01``; the handler submits that id as-is."""
        ws, project, experiment, run = _make_run(tmp_path)
        _precreate_e01(ws, project, run)
        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_transport", lambda _t: transport)
        captured = _install_fake_submitor(monkeypatch, run)

        handler = _remote_handler()
        handler(None, run, experiment, project, execution_id="e01")

        assert captured["submit_metadata"]["execution_id"] == "e01"
        assert captured["submit_cwd"].endswith("/executions/e01")
        argv = captured["submit_argv"]
        flag = argv.index("--execution-id")
        assert argv[flag : flag + 2] == ["--execution-id", "e01"]
        assert [e.id for e in run.executions] == ["e01"]
        (e01,) = run.executions
        assert e01.executor["job_id"] == "fake-job-id"
        assert e01.executor["scheduler"] == "slurm"

    def test_cli_path_submits_a_precreated_enn_execution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The CLI path passes no id; the attempt must still be a workspace ``eNN``."""
        _ws, project, experiment, run = _make_run(tmp_path)
        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_transport", lambda _t: transport)
        captured = _install_fake_submitor(monkeypatch, run)

        handler = _remote_handler()
        handler(None, run, experiment, project)

        execution_id = captured["submit_metadata"]["execution_id"]
        assert re.fullmatch(r"e\d{2,}", execution_id)
        assert (execution_id, "queued") in captured["records_at_submit"]

    def test_remote_staging_carries_the_execution_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The remote worker reads its QUEUED record, so stage-in must carry it."""
        ws, project, experiment, run = _make_run(tmp_path)
        _precreate_e01(ws, project, run)
        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_transport", lambda _t: transport)
        _install_fake_submitor(monkeypatch, run)

        handler = _remote_handler()
        handler(None, run, experiment, project, execution_id="e01")

        record = Path(run.run_dir) / "executions" / "e01" / "execution.json"
        assert record.is_file()
        assert _uploads_cover(transport.calls, record)
