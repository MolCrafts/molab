"""SubmitHandler must route through the target's transport when one is set.

Uses a fake transport that records every shell call + file op, plus a fake
molq ``Submitor`` so we don't need a working SSH endpoint or a real worker
subprocess.  The assertions cover the wiring — with-target vs no-target — not
the worker behaviour, which is exercised by the molq suite.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest

from molab.plugins.submit_molq.submit import encode_job_ref
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
        registry_id="reg",
        cluster_id="hpc",
        scratch_root="/scratch/me/molab",
    )


def _remote_handler():
    from molab.plugins.submit_molq.submit import make_submit_handler

    return make_submit_handler(
        scheduler="ignored-when-target-set",
        cluster="local",
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


_FAKE_REF = {
    "registry_id": "reg",
    "cluster_id": "hpc",
    "native_id": "fake-sched-id",
    "incarnation": "1",
}
_JOB_ID = encode_job_ref(_FAKE_REF)


def _install_fake_session(monkeypatch: pytest.MonkeyPatch, run, captured: dict[str, Any]) -> None:
    """Replace the application client and record the submitted spec."""

    class _FakeJob:
        def __init__(self) -> None:
            self.ref = dict(_FAKE_REF)

    class _FakeCluster:
        def __init__(self, name: str) -> None:
            captured["cluster"] = name

        def submit(self, spec, *, argv=None, request_key=None):
            del argv, request_key
            unit = spec.execution.units[0]
            captured["submit_argv"] = list(unit.command.get("argv") or [])
            captured["submit_cwd"] = unit.cwd
            captured["submit_env"] = dict(spec.execution.env or {})
            captured["records_at_submit"] = [(e.id, e.status.value) for e in run.executions]
            return _FakeJob()

    class _FakeMolq:
        def cluster(self, name: str) -> _FakeCluster:
            return _FakeCluster(name)

    def _session(_registry_id=None):
        return _FakeMolq()

    monkeypatch.setattr("molab.workspace.connection.get_client", _session)
    monkeypatch.setattr(
        "molab.workspace.targets.target_definition", lambda _t: {"id": "hpc", "scheduler": "slurm"}
    )


class TestSubmitHandler:
    def test_with_target_stages_in_and_routes_through_transport(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, project, experiment, run = _make_run(tmp_path)
        target = ComputeTarget(
            name="hpc",
            registry_id="reg",
            cluster_id="hpc",
            scratch_root="/scratch/me/molab",
        )

        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: transport)

        captured_submitor: dict[str, Any] = {}
        _install_fake_session(monkeypatch, run, captured_submitor)

        from molab.plugins.submit_molq.submit import make_submit_handler

        handler = make_submit_handler(
            scheduler="ignored-when-target-set",
            cluster="local",
            resources={},
            scheduling={},
            target=target,
        )
        handler(None, run, experiment, project)

        # Stage-in happened: the run dir, then the one attempt's directory.
        uploads = [c for c in transport.calls if c[0] == "upload"]
        assert len(uploads) == 5
        src, dst = uploads[0][1]
        assert src == str(Path(run.run_dir).resolve())
        assert dst.startswith("/scratch/me/molab/")
        assert run.execution("e01").executor["remote_run_dir"] == dst
        exec_src, exec_dst = uploads[1][1]
        assert exec_src.endswith("/executions/e01")
        assert exec_dst.startswith("/scratch/me/molab/")
        assert exec_dst.endswith("/executions/e01")

        # The registered cluster is the handler default; the target's scheduler
        # is recorded on the attempt, not passed into molq.
        assert captured_submitor["cluster"] == "hpc"
        assert run.execution("e01").executor["scheduler"] == "slurm"
        # The worker is told to chdir into the remote exec dir.
        assert captured_submitor["submit_cwd"].startswith("/scratch/me/molab/")
        assert "executions/" in captured_submitor["submit_cwd"]
        # Argv points at the remote run dir, not the local one.
        argv = captured_submitor["submit_argv"]
        assert "molab.cli" in argv and "execute" in argv
        assert any(a.startswith("/scratch/me/molab/") for a in argv)

    def test_without_target_submits_the_local_attempt_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """No-target path does not stage; the worker cwd is the local attempt dir."""
        _, project, experiment, run = _make_run(tmp_path)
        captured: dict[str, Any] = {}
        _install_fake_session(monkeypatch, run, captured)

        from molab.plugins.submit_molq.submit import make_submit_handler

        handler = make_submit_handler(
            scheduler="shell",
            cluster="local",
            resources={},
            scheduling={},
            target=None,
        )
        handler(None, run, experiment, project)

        assert captured["submit_cwd"].startswith(str(run.run_dir))
        assert captured["submit_cwd"].endswith("/executions/e01")

    def test_precreated_execution_id_is_submitted_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The server path precreates ``e01``; the handler submits that id as-is."""
        ws, project, experiment, run = _make_run(tmp_path)
        _precreate_e01(ws, project, run)
        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: transport)
        captured: dict[str, Any] = {}
        _install_fake_session(monkeypatch, run, captured)

        handler = _remote_handler()
        handler(None, run, experiment, project, execution_id="e01")

        assert captured["submit_env"]["MOLAB_EXECUTION_ID"] == "e01"
        assert captured["submit_cwd"].endswith("/executions/e01")
        argv = captured["submit_argv"]
        flag = argv.index("--execution-id")
        assert argv[flag : flag + 2] == ["--execution-id", "e01"]
        assert [e.id for e in run.executions] == ["e01"]
        (e01,) = run.executions
        assert e01.executor["job_id"] == _JOB_ID
        assert e01.executor["scheduler"] == "slurm"

    def test_cli_path_submits_a_precreated_enn_execution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The CLI path passes no id; the attempt must still be a workspace ``eNN``."""
        _ws, project, experiment, run = _make_run(tmp_path)
        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: transport)
        captured: dict[str, Any] = {}
        _install_fake_session(monkeypatch, run, captured)

        handler = _remote_handler()
        handler(None, run, experiment, project)

        execution_id = captured["submit_env"]["MOLAB_EXECUTION_ID"]
        assert re.fullmatch(r"e\d{2,}", execution_id)
        assert (execution_id, "queued") in captured["records_at_submit"]

    def test_remote_staging_carries_the_execution_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The remote worker reads its QUEUED record, so stage-in must carry it."""
        ws, project, experiment, run = _make_run(tmp_path)
        _precreate_e01(ws, project, run)
        transport = RecordingTransport()
        monkeypatch.setattr("molab.workspace.targets.to_filesystem", lambda _t: transport)
        _install_fake_session(monkeypatch, run, {})

        handler = _remote_handler()
        handler(None, run, experiment, project, execution_id="e01")

        record = Path(run.run_dir) / "executions" / "e01" / "execution.json"
        assert record.is_file()
        assert _uploads_cover(transport.calls, record)


class _CopyTransport:
    """Copies a tree on the local disk, honoring ``exclude`` name patterns."""

    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> None:
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)

    def upload(
        self,
        local: str,
        remote: str,
        *,
        recursive: bool = False,
        exclude: tuple[str, ...] = (),
    ) -> None:
        del recursive
        src = Path(local)
        dst = Path(remote)

        def _ignore(_directory: str, names: list[str]) -> list[str]:
            return [name for name in names if any(fnmatch(name, pattern) for pattern in exclude)]

        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def download(
        self,
        remote: str,
        local: str,
        *,
        recursive: bool = False,
        exclude: tuple[str, ...] = (),
    ) -> None:
        self.upload(remote, local, recursive=recursive, exclude=exclude)

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")


_HEALED_MODULE = """\
from molab.workflow import Workflow, WorkflowCompiler

wf = Workflow(name="staged")


@wf.task
def stage_a(seed: int) -> int:
    return seed + 1


@wf.task(depends_on=["stage_a"])
def stage_b(stage_a: int) -> int:
    return stage_a * 100


workflow = WorkflowCompiler().compile(wf)
"""


class TestRemoteWorkerOpensStagedAttempt:
    @pytest.mark.parametrize("entry_kind", ["file", "package", "captured"])
    def test_worker_runs_from_a_staged_only_layout(self, tmp_path: Path, entry_kind: str) -> None:
        """The worker must run from exactly what ``stage_in`` uploads.

        The remote host holds ``<scratch_root>/<ws>/<project>/<exp>/<run>`` —
        the run dir without ``executions/`` plus ``executions/e01/`` — and no
        ``workspace.json`` / ``experiment.json`` above it.
        """
        from molab.plugins.submit_molq.staging import stage_in
        from molab.workspace.targets import target_run_dir

        wf_file = tmp_path / "staged_wf.py"
        helper = tmp_path / "staged_helper.py"
        helper.write_text("def increment(value):\n    return value + 1\n", encoding="utf-8")
        wf_file.write_text(
            "from staged_helper import increment\n"
            + _HEALED_MODULE.replace("return seed + 1", "return increment(seed)"),
            encoding="utf-8",
        )
        ws = Workspace(root=tmp_path / "ws", name="remote-lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        # Hand-written binding (arch-own-04 replaces this with Experiment.bind_workflow).
        entrypoint = wf_file
        if entry_kind == "package":
            entrypoint = tmp_path / "staged_package"
            entrypoint.mkdir()
            (entrypoint / "step.py").write_text(helper.read_text(), encoding="utf-8")
            (entrypoint / "__init__.py").write_text(
                "from staged_package.step import increment\n"
                + _HEALED_MODULE.replace("return seed + 1", "return increment(seed)"),
                encoding="utf-8",
            )
        experiment.bind_workflow("code", entrypoint=f"{entrypoint}:workflow")
        run = experiment.add_run(params={"seed": 1})
        run.materialize()
        queued = run._create_execution(
            source_entrypoint=wf_file if entry_kind == "captured" else None
        )
        if entry_kind == "captured":
            wf_file.write_text("raise RuntimeError('changed after queueing')", encoding="utf-8")
        assert queued.id == "e01"

        # The "remote host": a scratch tree disjoint from the workspace, filled by
        # the production stage_in through a local-copy transport.
        target = ComputeTarget(
            name="hpc",
            registry_id="reg",
            cluster_id="hpc",
            scratch_root=str(tmp_path / "scratch"),
        )
        original_experiment = (
            Path(str(experiment.experiment_dir)) / "experiment.json"
        ).read_bytes()
        stage_in(_CopyTransport(), run, target, "e01")
        assert (
            Path(str(experiment.experiment_dir)) / "experiment.json"
        ).read_bytes() == original_experiment
        staged_run_dir = Path(target_run_dir(target, ws, run))
        staged_record = staged_run_dir / "executions" / "e01" / "execution.json"
        assert (staged_run_dir / "run.json").is_file()
        assert staged_record.is_file()
        assert any((d / "workspace.json").exists() for d in staged_run_dir.parents)
        # Remove all original context and source: a memo or shared source path cannot hide a missing input.
        shutil.rmtree(ws.root)
        wf_file.unlink()
        helper.unlink()
        if entry_kind == "package":
            shutil.rmtree(entrypoint)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "molab.cli",
                "execute",
                str(staged_run_dir),
                "--execution-id",
                "e01",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        record = json.loads(staged_record.read_text(encoding="utf-8"))
        assert record["status"] == "succeeded"
