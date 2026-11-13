"""Stage-in / stage-out for remote compute targets.

When a Run executes on a non-local :class:`~molab.workspace.ComputeTarget`,
its working directory must exist on the remote filesystem before the worker
starts and its outputs must come back to the local workspace afterwards.
This module chooses which experiment files to transfer using the destination's
file adapter. All authentication, native file operations and transfer execution
belong to molq. No transport implementation is kept in molab.

The local↔remote contract is intentionally narrow:

* **Stage-in** mirrors the local ``run_dir`` (its ``index.md`` record and
  the other run-level files) into ``target_run_dir`` on the transport's filesystem,
  excluding ``executions/`` and Python bytecode, so no other attempt on the
  remote side is overwritten by a stale local copy. It then uploads the one
  attempt being submitted, ``executions/<id>/``, which carries the QUEUED
  ``execution.json`` the remote worker opens. The run's ``values/`` store
  rides the run-dir mirror; for a RESUME or a partial RERUN the predecessor's
  journal (``executions/<based_on>/workflow.json``) and its ``nodes/`` journals
  are uploaded too, so the worker seeds from the same records it would locally.
  The isolated namespace also
  receives the selected ancestor ``index.md`` records and workflow code/document;
  code bindings are rewritten only in a temporary staging copy. An existing
  Execution source snapshot takes precedence over the live entrypoint. Each
  asset the run names in ``inputs`` is uploaded as its whole slot to the same
  place in the namespace, with its host's record, so the worker resolves the
  ``molab:asset`` ref there as it would locally. So is each product an
  earlier attempt of this run registered, so a later attempt re-registers
  into that slot under the same id.
* **Stage-out** pulls the remote ``executions/<id>/`` back **without** its
  ``execution.json`` (products, logs, the per-attempt ``alive`` heartbeat)
  and the run's ``values/`` store (the content-addressed values the pulled
  journal cites; rsync adds only the new files), then reads the remote
  ``execution.json`` and hands it to
  :meth:`~molab.workspace.execution_repository.ExecutionRepository.merge_remote`.
  Before the merge, every asset the attempt registered in its staged
  experiment comes back with the id the worker minted, installed by the
  experiment's repository (``AssetRepository.adopt``); a product that cannot
  take its slot here (another asset owns the slug or the bytes) raises and
  leaves the local record unmerged.
  The plugin only moves bytes and decodes JSON; the workspace owns the record
  and decides how the worker's state and the local job ids combine. The
  run-level ``index.md`` is never pulled (its record is immutable and was
  uploaded by stage-in; the local owner rewrites its derived index), and neither is a run-root ``alive`` (the heartbeat is per
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
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol

from molq import MolqError

from molab.ids import hash_bytes
from molab.workspace import Workspace
from molab.workspace.asset_repository import asset_by_id
from molab.workspace.domain import Asset, ExecutionMode, ExecutionOrigin
from molab.workspace.entity_record import ENTITY_FILENAME
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.naming import ASSET_CONTAINER, VALUE_CONTAINER
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

    def exists(self, path: str) -> bool: ...

    def glob(self, path: str, pattern: str) -> Iterable[str]: ...


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
    _stage_predecessor_journal(transport, mol_run, execution_id, src, dst)

    # One private workspace namespace per run: concurrent runs never overwrite
    # each other's workflow binding. Only selected ancestor metadata is staged.
    root = Path(str(workspace.root)).resolve()
    destination_root = _staged_root(dst, mol_run)
    experiment = mol_run.experiment
    project = experiment.project
    records = [
        root / ENTITY_FILENAME,
        Path(str(project.project_dir)) / ENTITY_FILENAME,
        Path(str(experiment.experiment_dir)) / ENTITY_FILENAME,
    ]
    for host in _stage_assets(transport, mol_run, destination_root):
        if host / ENTITY_FILENAME not in records:
            records.append(host / ENTITY_FILENAME)
    with tempfile.TemporaryDirectory(prefix="molab-worker-") as temporary:
        bundle = Path(temporary)
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
            # Only the entrypoint moves; the graph IR ``define`` stored stays.
            staged_experiment.bind_workflow(
                "code",
                entrypoint=f"{code_remote}:{qualname}",
                document=staged_experiment.workflow_document,
            )
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


def _staged_root(remote_run: str, mol_run: Run) -> PurePosixPath:
    """The workspace root of *mol_run*'s private namespace, given its remote run dir."""
    workspace = mol_run.experiment.project.workspace
    relative = Path(mol_run.run_dir).resolve().relative_to(Path(str(workspace.root)).resolve())
    staged = PurePosixPath(remote_run)
    for _part in relative.parts:
        staged = staged.parent
    return staged


def _stage_assets(
    transport: StagingFiles, mol_run: Run, destination_root: PurePosixPath
) -> list[Path]:
    """Upload the asset slots the run needs to the same place in the staged workspace.

    These are each asset the run names in ``inputs``, and each product an
    earlier attempt of this run registered: the worker then finds that slot
    occupied and re-registers into it under the same id, as it would here.

    Returns:
        The host directories those slots belong to, whose records the staged
        workspace needs to find them.

    Raises:
        ValueError: An input names no asset of this workspace.
    """
    workspace = mol_run.experiment.project.workspace
    root = Path(str(workspace.root)).resolve()
    needed: list[Asset] = []
    for asset_id in mol_run.inputs:
        asset = asset_by_id(workspace, asset_id)
        if asset is None:
            raise ValueError(f"input asset {asset_id} is not in this workspace")
        needed.append(asset)
    needed.extend(
        asset
        for asset in mol_run.experiment.assets.list()
        if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == mol_run.id
    )
    hosts: list[Path] = []
    for asset in needed:
        repository = workspace.assets_at(asset.scope)
        slug = repository.find_slug(asset.id)
        assert slug is not None
        host = Path(repository.scope_dir).resolve()
        remote = destination_root / host.relative_to(root) / ASSET_CONTAINER / slug
        transport.mkdir(str(remote), parents=True, exist_ok=True)
        transport.upload(
            str(host / ASSET_CONTAINER / slug), str(remote), recursive=True, exclude=_RSYNC_EXCLUDES
        )
        hosts.append(host)
    return hosts


def _stage_predecessor_journal(
    transport: StagingFiles, mol_run: Run, execution_id: str, src: str, dst: str
) -> None:
    """Upload the journal a RESUME / partial RERUN seeds from, when there is one."""
    record = mol_run.execution(execution_id)
    based_on = record.based_on_execution_id
    seeded = record.mode is ExecutionMode.RESUME or (
        record.mode is ExecutionMode.RERUN and bool(record.selected_tasks)
    )
    if not based_on or not seeded:
        return
    journal = Path(src) / "executions" / based_on / "workflow.json"
    if not journal.is_file():
        return
    remote_dir = f"{dst}/executions/{based_on}"
    transport.mkdir(remote_dir, parents=True, exist_ok=True)
    transport.upload(str(journal), f"{remote_dir}/workflow.json")
    nodes = Path(src) / "executions" / based_on / "nodes"
    if nodes.is_dir():
        remote_nodes = f"{remote_dir}/nodes"
        transport.mkdir(remote_nodes, parents=True, exist_ok=True)
        transport.upload(str(nodes), remote_nodes, recursive=True, exclude=_RSYNC_EXCLUDES)


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
        _pull_values(transport, remote_run, local_run)
        text = transport.read_text(f"{remote_exec}/execution.json")
        _pull_products(transport, mol_run, execution_id, _staged_root(remote_run, mol_run))
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


def _pull_products(
    transport: StagingFiles, mol_run: Run, execution_id: str, staged_root: PurePosixPath
) -> None:
    """Bring back every asset attempt *execution_id* registered in its staged experiment.

    Each slot keeps the id the worker minted; the experiment's repository
    installs it (:meth:`~molab.workspace.asset_repository.AssetRepository.adopt`).
    A slot already here with the same bytes and producer is not transferred again.

    Raises:
        ValueError: A product cannot take its slot here (see ``adopt``).
    """
    workspace = mol_run.experiment.project.workspace
    experiment_dir = Path(str(mol_run.experiment.experiment_dir)).resolve()
    relative = experiment_dir.relative_to(Path(str(workspace.root)).resolve())
    remote_assets = staged_root / relative / ASSET_CONTAINER
    if not transport.exists(str(remote_assets)):
        return
    repository = mol_run.experiment.assets
    for record in sorted(transport.glob(str(remote_assets), "*/asset.json")):
        raw = json.loads(transport.read_text(record))
        origin = raw.get("origin") or {}
        if origin.get("run_id") != mol_run.id or origin.get("execution_id") != execution_id:
            continue
        local = asset_by_id(workspace, raw["id"])
        if (
            local is not None
            and local.content.digest == raw["content"]["digest"]
            and local.origin.model_dump(mode="json") == origin
        ):
            continue
        slot = PurePosixPath(record).parent
        with tempfile.TemporaryDirectory(prefix="molab-product-") as temporary:
            pulled = Path(temporary) / slot.name
            pulled.mkdir()
            transport.download(str(slot), str(pulled), recursive=True, exclude=_RSYNC_EXCLUDES)
            repository.adopt(pulled)


def _pull_values(transport: StagingFiles, remote_run: str, local_run: str) -> None:
    """Pull the run's ``values/`` store back; a remote run without one has nothing to pull."""
    remote_values = f"{remote_run}/{VALUE_CONTAINER}"
    if not transport.exists(remote_values):
        return
    local_values = Path(local_run) / VALUE_CONTAINER
    local_values.mkdir(parents=True, exist_ok=True)
    transport.download(remote_values, str(local_values), recursive=True, exclude=_RSYNC_EXCLUDES)


__all__ = ["StagingFiles", "stage_in", "stage_out"]
