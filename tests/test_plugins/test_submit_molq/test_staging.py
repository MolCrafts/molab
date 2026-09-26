"""Tests for ``stage_in`` / ``stage_out`` using a fake transport.

The fake records every upload/download/mkdir (with its ``exclude`` patterns)
and serves ``read_text`` from a dict, so the tests assert on the
local<->remote transfer contract without a real SSH endpoint.

arch-own-02d: stage-in uploads the run dir (without ``executions/``) and then
the one attempt's ``executions/<id>/``; stage-out pulls only the attempt dir
(without ``execution.json``), reads the remote record and merges it through
``ExecutionRepository.merge_remote``, returning whether the local record now
reflects the worker's.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from molq.transport import CommandResult, TransportError

from molab.plugins.submit_molq import staging as staging_mod
from molab.plugins.submit_molq.staging import _RSYNC_EXCLUDES, stage_in, stage_out
from molab.workspace import ComputeTarget, Run, Workspace
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.targets import target_run_dir

Transfer = tuple[str, str, bool, tuple[str, ...]]


@dataclass
class FakeTransport:
    """Records every call so tests can assert on uploads / downloads."""

    uploads: list[Transfer] = field(default_factory=list)
    downloads: list[Transfer] = field(default_factory=list)
    mkdirs: list[str] = field(default_factory=list)
    existing: set[str] = field(default_factory=set)
    raise_on_download: set[str] = field(default_factory=set)
    texts: dict[str, str] = field(default_factory=dict)

    def run(self, *_a: Any, **_kw: Any) -> CommandResult:
        return CommandResult(argv=(), returncode=0, stdout="", stderr="")

    def read_text(self, path: str) -> str:
        if path not in self.texts:
            raise TransportError("no such file", remote=path)
        return self.texts[path]

    def read_bytes(self, path: str) -> bytes:
        return b""

    def write_text(self, path: str, data: str, *, mode: int = 0o600) -> None:
        return None

    def write_bytes(self, path: str, data: bytes, *, mode: int = 0o600) -> None:
        return None

    def exists(self, path: str) -> bool:
        return path in self.existing

    def mkdir(self, path: str, *, parents: bool = True, exist_ok: bool = True) -> None:
        self.mkdirs.append(path)

    def chmod(self, path: str, mode: int) -> None:
        return None

    def remove(self, path: str, *, recursive: bool = False) -> None:
        return None

    def upload(
        self,
        local: str,
        remote: str,
        *,
        recursive: bool = False,
        exclude: Sequence[str] = (),
    ) -> None:
        self.uploads.append((local, remote, recursive, tuple(exclude)))

    def download(
        self,
        remote: str,
        local: str,
        *,
        recursive: bool = False,
        exclude: Sequence[str] = (),
    ) -> None:
        if remote in self.raise_on_download:
            raise TransportError("simulated", remote=remote)
        self.downloads.append((remote, local, recursive, tuple(exclude)))


def _make_run(tmp_path: Path) -> tuple[Workspace, Run]:
    """Create a workspace + project + experiment + run hierarchy on disk."""
    ws = Workspace(tmp_path)
    ws.materialize()
    project = ws.add_project("p")
    experiment = project.add_experiment("e", params={})
    run = experiment.add_run(params={"seed": 1})
    return ws, run


def _remote_target() -> ComputeTarget:
    return ComputeTarget(name="hpc", host="me@h", scheduler="slurm", scratch_root="/scratch")


def _repo(ws: Workspace, run: Run) -> ExecutionRepository:
    return ExecutionRepository(
        ws.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=ws.fs,
    )


def _queued_with_job_id(ws: Workspace, run: Run) -> None:
    """Local QUEUED ``e01`` carrying the scheduler job id molq recorded."""
    run.create_execution(executor={"backend": "molq", "target": "hpc"})
    _repo(ws, run).update_operational(
        "e01", executor={"backend": "molq", "target": "hpc", "job_id": "j-1"}
    )


def _remote_doc(run: Run) -> str:
    """The worker's sealed record of ``e01`` as it sits on the remote host."""
    local = run.execution("e01")
    doc: dict[str, object] = {
        "schema_version": 4,
        **local.model_dump(mode="json"),
        "status": "succeeded",
        "started_at": "2026-01-01T00:00:01Z",
        "finished_at": "2026-01-01T00:00:09Z",
        "sealed_at": "2026-01-01T00:00:10Z",
        "sealed_commit": "deadbeef",
        "executor": {"backend": "molq", "kind": "local", "host": "node7", "pid": 42},
        "environment": {**local.environment, "host": "node7"},
    }
    return json.dumps(doc)


def _record_bytes(run: Run, execution_id: str = "e01") -> bytes:
    return (Path(run.run_dir) / "executions" / execution_id / "execution.json").read_bytes()


class TestStageIn:
    def test_noop_when_target_dir_equals_run_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Local target whose computed run dir == run.run_dir → no rsync."""
        _ws, run = _make_run(tmp_path)
        target = ComputeTarget(name="loop", scratch_root=str(tmp_path))
        monkeypatch.setattr(staging_mod, "target_run_dir", lambda *_a, **_kw: str(run.run_dir))

        transport = FakeTransport()
        stage_in(transport, run, target, "e01")

        assert transport.uploads == []
        assert transport.mkdirs == []

    def test_remote_uploads_run_dir_after_mkdir(self, tmp_path: Path) -> None:
        _ws, run = _make_run(tmp_path)
        run.create_execution()
        transport = FakeTransport()

        stage_in(transport, run, _remote_target(), "e01")

        src, dst, recursive, _exclude = transport.uploads[0]
        assert src == str(Path(run.run_dir).resolve())
        assert dst.startswith("/scratch/")
        assert dst.endswith(f"/{run.id}")
        assert recursive is True
        # Ensures the target dir was created before upload.
        assert dst in transport.mkdirs

    def test_remote_uploads_run_dir_then_execution_dir(self, tmp_path: Path) -> None:
        _ws, run = _make_run(tmp_path)
        run.create_execution()
        transport = FakeTransport()

        stage_in(transport, run, _remote_target(), "e01")

        assert len(transport.uploads) == 2
        src, dst, recursive, exclude = transport.uploads[0]
        assert recursive is True
        assert "executions" in exclude
        assert transport.uploads[1] == (
            str(Path(src) / "executions" / "e01"),
            f"{dst}/executions/e01",
            True,
            _RSYNC_EXCLUDES,
        )
        assert f"{dst}/executions/e01" in transport.mkdirs


class TestStageOut:
    def test_noop_when_remote_dir_equals_run_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, run = _make_run(tmp_path)
        target = ComputeTarget(name="loop", scratch_root="/tmp")
        monkeypatch.setattr(staging_mod, "target_run_dir", lambda *_a, **_kw: str(run.run_dir))

        transport = FakeTransport()
        result = stage_out(transport, run, target, "exec-1")

        assert transport.downloads == []
        assert result is True

    def test_remote_pulls_only_the_attempt_dir(self, tmp_path: Path) -> None:
        _ws, run = _make_run(tmp_path)
        transport = FakeTransport()

        result = stage_out(transport, run, _remote_target(), "exec-abc")

        remote_paths = [d[0] for d in transport.downloads]
        assert len(remote_paths) == 1
        assert remote_paths[0].endswith("/executions/exec-abc")
        assert not any(p.endswith("/run.json") for p in remote_paths)
        assert not any(p.endswith("/alive") for p in remote_paths)
        # No ``texts`` → the remote record is unreadable → not authoritative.
        assert result is False

    def test_exec_dir_pull_excludes_execution_json(self, tmp_path: Path) -> None:
        _ws, run = _make_run(tmp_path)
        transport = FakeTransport()

        stage_out(transport, run, _remote_target(), "exec-abc")

        _remote, _local, _recursive, exclude = transport.downloads[0]
        assert "execution.json" in exclude

    def test_swallows_transport_error_on_download(self, tmp_path: Path) -> None:
        """A TransportError on the exec-dir pull is swallowed, never raised."""
        _ws, run = _make_run(tmp_path)
        ws = run.experiment.project.workspace
        transport = FakeTransport(
            raise_on_download={
                f"/scratch/{ws.metadata.id}/{run.experiment.project.id}/"
                f"{run.experiment.id}/{run.id}/executions/exec-x"
            }
        )
        result = stage_out(transport, run, _remote_target(), "exec-x")  # must not raise

        assert result is False

    def test_merges_remote_record_keeping_local_executor(self, tmp_path: Path) -> None:
        ws, run = _make_run(tmp_path)
        _queued_with_job_id(ws, run)
        target = _remote_target()
        remote_record = f"{target_run_dir(target, ws, run)}/executions/e01/execution.json"
        transport = FakeTransport(texts={remote_record: _remote_doc(run)})

        result = stage_out(transport, run, target, "e01")

        merged = run.execution("e01")
        assert merged.status.value == "succeeded"
        assert merged.executor["job_id"] == "j-1"
        assert merged.executor["host"] == "node7"
        assert result is True

        after_first = _record_bytes(run)
        stage_out(transport, run, target, "e01")
        assert _record_bytes(run) == after_first

    def test_missing_remote_record_leaves_local_untouched(self, tmp_path: Path) -> None:
        ws, run = _make_run(tmp_path)
        _queued_with_job_id(ws, run)
        before = run.execution("e01")
        transport = FakeTransport()

        result = stage_out(transport, run, _remote_target(), "e01")

        assert run.execution("e01") == before
        assert result is False
