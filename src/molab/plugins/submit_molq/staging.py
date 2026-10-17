"""Stage-in / stage-out for remote compute targets.

When a Run executes on a non-local :class:`~molab.workspace.ComputeTarget`,
its working directory must exist on the remote filesystem before the worker
starts and its outputs must come back to the local workspace afterwards.
This module owns those two transfers via the molq :class:`~molq.transport.Transport`.

The local↔remote contract is intentionally narrow:

* **Stage-in** mirrors the local ``run_dir`` (run.json and the other
  run-level files) into ``target_run_dir`` on the transport's filesystem,
  excluding ``executions/`` and Python bytecode, so no other attempt on the
  remote side is overwritten by a stale local copy. It then uploads the one
  attempt being submitted, ``executions/<id>/``, which carries the QUEUED
  ``execution.json`` the remote worker opens.
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
from pathlib import Path
from typing import TYPE_CHECKING

from molq.transport import Transport, TransportError

from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.targets import target_run_dir

if TYPE_CHECKING:
    from molab.workspace import ComputeTarget, Run


_RSYNC_EXCLUDES = ("__pycache__", "*.pyc", "*.pyo", ".DS_Store")


def stage_in(
    transport: Transport,
    mol_run: Run,
    target: ComputeTarget,
    execution_id: str,
) -> None:
    """Mirror the local run dir and one attempt's directory to the target.

    The run dir is uploaded without ``executions/`` so no other attempt on the
    remote side is overwritten; then ``executions/<execution_id>/`` is
    uploaded on its own, so the remote worker finds the QUEUED record it is
    told to open. No-op when source and destination are the same path (a
    local target with no scratch override).

    Args:
        transport: The target's molq transport.
        mol_run: The run being submitted.
        target: The compute target the run executes on.
        execution_id: The attempt being submitted (``e01``); its record must
            already exist locally.

    Raises:
        TransportError: An upload or mkdir on the target failed.
    """
    src = str(Path(mol_run.run_dir).resolve())
    workspace = mol_run.experiment.project.workspace
    dst = target_run_dir(target, workspace, mol_run)
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


def stage_out(
    transport: Transport,
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
        transport: The target's molq transport.
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
    remote_run = target_run_dir(target, workspace, mol_run)
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
    except TransportError:
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


__all__ = ["stage_in", "stage_out"]
