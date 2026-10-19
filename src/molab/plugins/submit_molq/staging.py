"""Stage-in / stage-out for remote compute targets.

When a Run executes on a non-local :class:`~molab.workspace.ComputeTarget`,
its working directory must exist on the remote filesystem before the worker
starts and its outputs must come back to the local workspace afterwards.
This module chooses which experiment files to transfer using the destination's
file adapter. All authentication, native file operations and transfer execution
belong to molq. No transport implementation is kept in molab.

The local↔remote contract is intentionally narrow:

* **Stage-in** mirrors the local ``run_dir`` (run.json and the other
  run-level files) into ``target_run_dir`` on the transport's filesystem,
  excluding ``executions/`` and Python bytecode, so no other attempt on the
  remote side is overwritten by a stale local copy. It then uploads the one
  attempt being submitted, ``executions/<id>/``, which carries the QUEUED
  ``execution.json`` the remote worker opens. The isolated namespace also
  receives the selected ancestor entity files and workflow code/document;
  code bindings are rewritten only in a temporary staging copy. An existing
  Execution source snapshot takes precedence over the live entrypoint.
* **Stage-out** pulls the remote ``executions/<id>/`` back **without** its
  ``execution.json`` (products, logs, the per-attempt ``alive`` heartbeat),
  then reads the remote ``execution.json`` and hands it to
  :meth:`~molab.workspace.execution_repository.ExecutionRepository.merge_remote`.
  The plugin only moves bytes and decodes JSON; the workspace owns the record
  and decides how the worker's state and the local job ids combine. The
  run-level ``run.json`` is never pulled (it is immutable and was uploaded by
  stage-in), and neither is a run-root ``alive`` (the heartbeat is per
  attempt).

Both operations are no-ops when the target's working dir resolves to the
local ``run_dir`` (i.e. a local target with no scratch-root override) so the
``--local`` path stays free of needless rsync calls.

Stage-out **must be idempotent** — molq's reconciler may fire the terminal
callback more than once during recovery. rsync makes the file pull
self-deduplicating, and merging into an already-sealed local record is a
no-op.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from molq import MolqError

from molab.ids import hash_bytes
from molab.workspace import Workspace
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.source_snapshot import SourceCaptureError, copy_sources, source_manifest
from molab.workspace.targets import target_run_dir

if TYPE_CHECKING:
    from molab.workspace import ComputeTarget, Run


_RSYNC_EXCLUDES = ("__pycache__", "*.pyc", "*.pyo", ".DS_Store")


class StagingFiles(Protocol):
    """The file operations stage-in and stage-out use."""

    def mkdir(self, path: str, *, parents: bool = ..., exist_ok: bool = ...) -> None: ...

    def upload(
        self,
        local: str,
        remote: str,
        *,
        recursive: bool = ...,
        exclude: Sequence[str] = ...,
    ) -> None: ...

    def download(
        self,
        remote: str,
        local: str,
        *,
        recursive: bool = ...,
        exclude: Sequence[str] = ...,
    ) -> None: ...

    def read_text(self, path: str) -> str: ...


def stage_in(
    transport: StagingFiles,
    mol_run: Run,
    target: ComputeTarget,
    execution_id: str,
    *,
    destination: str | None = None,
) -> None:
    """Mirror the local run dir and one attempt's directory to the target.

    The run dir is uploaded without ``executions/`` so no other attempt on the
    remote side is overwritten; then ``executions/<execution_id>/`` is
    uploaded on its own, so the remote worker finds the QUEUED record it is
    told to open. No-op when source and destination are the same path (a
    local target with no scratch override).

    Args:
        transport: The destination's file adapter.
        mol_run: The run being submitted.
        target: The compute target the run executes on.
        execution_id: The attempt being submitted (``e01``); its record must
            already exist locally.
        destination: Immutable run path resolved by the submitting operation.

    Raises:
        TransportError: An upload or mkdir on the target failed.
    """
    src = str(Path(mol_run.run_dir).resolve())
    workspace = mol_run.experiment.project.workspace
    dst = destination if destination is not None else target_run_dir(target, workspace, mol_run)
    if src == dst:
        return

    transport.mkdir(dst, parents=True, exist_ok=True)
    transport.upload(
        src,
        dst,
        recursive=True,
        exclude=(*_RSYNC_EXCLUDES, "executions"),
    )
    remote_exec = f"{dst}/executions/{execution_id}"
    transport.mkdir(remote_exec, parents=True, exist_ok=True)
    transport.upload(
        str(Path(src) / "executions" / execution_id),
        remote_exec,
        recursive=True,
        exclude=_RSYNC_EXCLUDES,
    )

    # One private workspace namespace per run: concurrent runs never overwrite
    # each other's workflow binding. Only selected ancestor metadata is staged.
    root = Path(str(workspace.root)).resolve()
    relative = Path(src).relative_to(root)
    destination_root = Path(dst)
    for _part in relative.parts:
        destination_root = destination_root.parent
    experiment = mol_run.experiment
    project = experiment.project
    with tempfile.TemporaryDirectory(prefix="molab-worker-") as temporary:
        bundle = Path(temporary)
        records = [
            root / "workspace.json",
            Path(str(project.project_dir)) / "project.json",
            Path(str(experiment.experiment_dir)) / "experiment.json",
        ]
        document = Path(str(experiment.experiment_dir)) / "workflow.ir.json"
        if document.is_file():
            records.append(document)
        for record in records:
            local = bundle / record.resolve().relative_to(root)
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(record, local)
        locator = experiment.entrypoint
        if experiment.workflow_kind == "code" and locator:
            source, qualname = locator.rsplit(":", 1)
            # Use the existing source-capture contract (file + first-party siblings).
            # Directory entrypoints are shipped as their package, without bytecode.
            code_relative = (
                Path(str(experiment.experiment_dir)).resolve().relative_to(root) / "source"
            )
            code_local = bundle / code_relative
            manifest = mol_run.execution(execution_id).source
            if manifest is not None:
                captured = Path(src) / "executions" / execution_id / "source"
                code_local.mkdir(parents=True, exist_ok=True)
                for entry in manifest.files:
                    original = captured / entry.name
                    if not original.resolve().is_relative_to(captured.resolve()):
                        raise SourceCaptureError("Captured source escapes its execution")
                    if hash_bytes(original.read_bytes()) != entry.sha256:
                        raise SourceCaptureError(f"Captured source changed: {entry.name}")
                    shutil.copy2(original, code_local / entry.name)
                code_remote = destination_root / code_relative / manifest.entrypoint
            elif Path(source).is_dir():
                shutil.copytree(
                    source,
                    code_local / Path(source).name,
                    ignore=shutil.ignore_patterns(*_RSYNC_EXCLUDES),
                )
                code_remote = destination_root / code_relative / Path(source).name
            else:
                capture_root = bundle / Path(str(experiment.experiment_dir)).resolve().relative_to(
                    root
                )
                copy_sources(source_manifest(source), capture_root)
                code_remote = destination_root / code_relative / Path(source).name
            staged_experiment = (
                Workspace.load(bundle).get_project(project.id).get_experiment(experiment.id)
            )
            staged_experiment.bind_workflow("code", entrypoint=f"{code_remote}:{qualname}")
            transport.mkdir(str(destination_root / code_relative), parents=True, exist_ok=True)
            transport.upload(
                str(code_local),
                str(destination_root / code_relative),
                recursive=True,
                exclude=_RSYNC_EXCLUDES,
            )
        for record in records:
            relative_record = record.resolve().relative_to(root)
            remote = destination_root / relative_record
            transport.mkdir(str(remote.parent), parents=True, exist_ok=True)
            transport.upload(str(bundle / relative_record), str(remote))


def stage_out(
    transport: StagingFiles,
    mol_run: Run,
    target: ComputeTarget,
    execution_id: str,
) -> bool:
    """Pull one attempt's files back and merge the worker's record locally.

    The remote ``executions/<execution_id>/`` is pulled without its
    ``execution.json``; the remote record is then read and merged through
    ``ExecutionRepository.merge_remote``, so the local job ids survive and a
    locally sealed record is never overwritten. Idempotent: a replayed call
    merges into an already-sealed record, which is a no-op.

    Args:
        transport: The destination's file adapter.
        mol_run: The run the attempt belongs to.
        target: The compute target the attempt ran on.
        execution_id: The attempt to pull back (``e01``).

    Returns:
        Whether the local record now reflects the worker's record: ``True``
        when the remote and local directories are the same path or the merge
        succeeded, ``False`` when the attempt directory or the remote
        ``execution.json`` could not be read (the local record is left as it
        was).

    Raises:
        KeyError: No local record ``execution_id`` exists.
        ValueError: The remote record is another attempt or rewrites a
            creation-time environment key.
    """
    workspace = mol_run.experiment.project.workspace
    record = next((item for item in mol_run.executions if item.id == execution_id), None)
    frozen_path = record.executor.get("remote_run_dir") if record is not None else None
    if frozen_path is not None and not isinstance(frozen_path, str):
        raise ValueError("Execution remote_run_dir must be a path string")
    remote_run = (
        frozen_path if frozen_path is not None else target_run_dir(target, workspace, mol_run)
    )
    local_run = str(Path(mol_run.run_dir).resolve())
    if remote_run == local_run:
        return True

    remote_exec = f"{remote_run}/executions/{execution_id}"
    local_exec = str(Path(local_run) / "executions" / execution_id)
    Path(local_exec).mkdir(parents=True, exist_ok=True)
    try:
        transport.download(
            remote_exec,
            local_exec,
            recursive=True,
            exclude=(*_RSYNC_EXCLUDES, "execution.json"),
        )
        text = transport.read_text(f"{remote_exec}/execution.json")
    except MolqError as exc:
        if exc.outcome == "unknown":
            raise
        return False
    except OSError:
        # The remote attempt dir or record may not exist yet (the job ended
        # before the worker wrote anything) or the host is unreachable —
        # leave the local record untouched.
        return False

    ExecutionRepository(
        workspace.root,
        mol_run.run_dir,
        run_id=mol_run.id,
        project_id=mol_run.experiment.project.id,
        fs=workspace.fs,
    ).merge_remote(execution_id, json.loads(text))
    return True


__all__ = ["StagingFiles", "stage_in", "stage_out"]
