"""``WorkspaceContext`` — the canonical workspace read-model + its assembler.

`WorkspaceContext` is the single structured projection the server, the CLI, and the
UI read so they reason over one shape instead of re-assembling workspace state
three ways. It is slice 01 of the P0.2 "WorkspaceContext
— full unification" chain (`.claude/notes/integration.md` §1).

Design invariants:

- **Pure projection.** :func:`assemble_workspace_context` is a read — it stores nothing
  new and the model is never itself canonical (authoritative state stays in the entity
  ``index.md`` records).
- **Layer-legal.** This module imports only ``workspace`` + stdlib/pydantic — never
  upstream layers (enforced by the workspace import-guard). Workflow
  *availability* is read workspace-only from the externalized ``workflow.json``.
- **Focus is caller-supplied.** :class:`ContextFocus` (active project/experiment/run +
  selected refs) is passed in, never persisted; it defaults to empty.
- **Health flags are computed, never stored** — and only the workspace-computable subset
  is produced here (``failed_run`` / ``stale_running`` / ``orphan_asset``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from molab._typing import JSONValue

from .experiment import Experiment
from .folder import WORKSPACE_EXPERIMENT_KIND, WORKSPACE_PROJECT_KIND
from .project import Project
from .run import Run
from .run_heartbeat import is_alive_stale
from .scope import as_folder, descendants, display_name

if TYPE_CHECKING:
    from .workspace import Workspace

# Aware-UTC floor for ordering runs that carry no timestamp (they sort last).
_TS_FLOOR = datetime(1970, 1, 1, tzinfo=UTC)

HealthFlagKind = Literal["failed_run", "stale_running", "orphan_asset"]


class WorkspaceRef(BaseModel, frozen=True):
    """Workspace identity."""

    id: str
    name: str
    root: str
    targets: list[str] = []


class ProjectRef(BaseModel, frozen=True):
    """A project's identity."""

    id: str
    name: str


class ExperimentRef(BaseModel, frozen=True):
    """An experiment's identity + its parameter-space summary."""

    id: str
    name: str
    project_id: str
    parameter_space: dict[str, JSONValue] = {}


class WorkflowRef(BaseModel, frozen=True):
    """An available workflow, read workspace-only from ``workflow.json``.

    ``ir_hash`` is left ``None`` in this slice (hashing the IR doc is deferred); the
    presence of a ``WorkflowRef`` means the experiment has a defined workflow.
    """

    experiment_id: str
    name: str
    ir_hash: str | None = None


class RunRef(BaseModel, frozen=True):
    """A run's identity + hot-state summary (from its record and Executions)."""

    run_id: str
    experiment_id: str
    project_id: str
    status: str
    definition_hash: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    current_execution_id: str | None = None


class ContextAsset(BaseModel, frozen=True):
    """One registered asset in the workspace read-model.

    ``path`` is workspace-relative and is the asset's payload, checked
    against its digest when the bytes can be resolved.
    """

    asset_id: str
    scope: str
    kind: str
    path: str
    content_hash: str | None = None
    run_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None


class HealthFlag(BaseModel, frozen=True):
    """A computed, workspace-derivable health signal (never stored)."""

    kind: HealthFlagKind
    ref: str
    detail: str


class ContextFocus(BaseModel, frozen=True):
    """Ephemeral, caller-supplied focus — never persisted as workspace state."""

    project_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None
    selected_object_refs: list[str] = []


class WorkspaceContext(BaseModel, frozen=True):
    """The canonical workspace read-model (integration.md §1.2 shape)."""

    workspace: WorkspaceRef
    focus: ContextFocus
    projects: list[ProjectRef] = []
    experiments: list[ExperimentRef] = []
    workflows: list[WorkflowRef] = []
    recent_runs: list[RunRef] = []
    failed_runs: list[RunRef] = []
    running_runs: list[RunRef] = []
    assets: list[ContextAsset] = []
    stale_or_missing: list[HealthFlag] = []


def _run_sort_key(ref: RunRef) -> datetime:
    ts = ref.finished_at or ref.started_at or _TS_FLOOR
    # Persisted run timestamps may be offset-naive (older writers); a mixed
    # naive/aware set must still sort. Naive values are treated as UTC.
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def assemble_workspace_context(
    workspace: Workspace,
    *,
    focus: ContextFocus | None = None,
    now: datetime | None = None,  # noqa: ARG001
) -> WorkspaceContext:
    """Assemble the canonical :class:`WorkspaceContext` — a pure read.

    Walks the authoritative folder tree + each run record and
    composes them into one read-model. Writes nothing.

    Args:
        workspace: The workspace to project.
        focus: Caller-supplied ephemeral focus (default: empty); echoed, never stored.
        now: Accepted for call-site compatibility; alive-mtime staleness uses
            wall clock, not this stamp.

    Returns:
        The assembled :class:`WorkspaceContext`.
    """
    focus = focus if focus is not None else ContextFocus()
    root = str(workspace.resolve())

    projects: list[ProjectRef] = []
    experiments: list[ExperimentRef] = []
    workflows: list[WorkflowRef] = []
    run_refs: list[RunRef] = []
    run_ids: set[str] = set()
    failed_runs: list[RunRef] = []
    running_runs: list[RunRef] = []
    flags: list[HealthFlag] = []

    folder = as_folder(workspace)
    for project in descendants(folder, Project):
        projects.append(ProjectRef(id=project.id, name=project.name))
    for experiment in descendants(folder, Experiment):
        experiments.append(
            ExperimentRef(
                id=experiment.id,
                name=experiment.name,
                project_id=experiment.ancestor_id(WORKSPACE_PROJECT_KIND),
                parameter_space=dict(experiment.parameter_space),
            )
        )
        if experiment.workflow_kind is not None:
            workflows.append(WorkflowRef(experiment_id=experiment.id, name=experiment.name))
    for run in descendants(folder, Run):
        # Ids above the serve boundary are not exposed: they read "" (a client
        # routes with "-" there).
        experiment_id = run.ancestor_id(WORKSPACE_EXPERIMENT_KIND)
        project_id = run.ancestor_id(WORKSPACE_PROJECT_KIND)
        executions = run.executions
        latest = executions[-1] if executions else None
        err = latest.error if latest else None
        err_text = (
            f"{err.get('type', 'Error')}: {err.get('message', '')}" if err is not None else None
        )
        status = run.status_label
        started = min(
            (e.started_at for e in executions if e.started_at is not None),
            default=None,
        )
        ref = RunRef(
            run_id=run.id,
            experiment_id=experiment_id,
            project_id=project_id,
            status=status,
            definition_hash=run.metadata.definition_hash,
            started_at=started,
            finished_at=latest.finished_at if latest else None,
            current_execution_id=latest.id if latest else None,
        )
        run_refs.append(ref)
        run_ids.add(run.id)
        if run.is_retryable:
            failed_runs.append(ref)
            # Say WHY, not just that it failed — the captured error is the
            # one signal a user needs to act (integration.md §1.4 "no
            # silent invalid state").
            reason = f": {err_text}" if err_text else ""
            flags.append(
                HealthFlag(
                    kind="failed_run",
                    ref=run.id,
                    detail=f"run {run.id} is {status} (retryable){reason}",
                )
            )
        # Any live attempt (queued / running / finalizing) counts. The
        # heartbeat check targets that attempt; a queued one has no
        # ``alive`` yet, and a missing ``alive`` is never stale.
        active_id = run.execution_id
        if active_id is not None:
            running_runs.append(ref)
            if is_alive_stale(run, active_id):
                flags.append(
                    HealthFlag(
                        kind="stale_running",
                        ref=run.id,
                        detail=f"run {run.id} is {status} but its heartbeat is stale",
                    )
                )

    recent_runs = sorted(run_refs, key=_run_sort_key, reverse=True)

    assets: list[ContextAsset] = []
    from .asset_repository import payload_path_for, scan_asset_repositories
    from .domain import ExecutionOrigin

    root_path = Path(root).resolve()
    for repository in scan_asset_repositories(workspace):
        for asset in repository.list():
            origin = asset.origin
            run_id = origin.run_id if isinstance(origin, ExecutionOrigin) else None
            execution_id = origin.execution_id if isinstance(origin, ExecutionOrigin) else None
            task_id = origin.task if isinstance(origin, ExecutionOrigin) else None
            relative = ""
            try:
                location = payload_path_for(workspace, asset.id)
            except (KeyError, ValueError, OSError):
                location = None
            if location is not None:
                try:
                    relative = Path(location).resolve().relative_to(root_path).as_posix()
                except ValueError:
                    relative = ""
            assets.append(
                ContextAsset(
                    asset_id=asset.id,
                    scope=asset.scope.urn,
                    kind="asset",
                    path=relative,
                    content_hash=asset.content.digest,
                    run_id=run_id,
                    execution_id=execution_id,
                    task_id=task_id,
                )
            )
            if run_id is not None and run_id not in run_ids:
                flags.append(
                    HealthFlag(
                        kind="orphan_asset",
                        ref=asset.id,
                        detail=(
                            f"asset {asset.id} names producer run {run_id!r}, which no longer resolves"
                        ),
                    )
                )

    host = folder.asset_host()
    targets = getattr(getattr(host, "metadata", None), "targets", None) or []
    return WorkspaceContext(
        workspace=WorkspaceRef(
            id=str(folder.metadata.id),
            name=display_name(folder),
            root=root,
            targets=[t.name for t in targets],
        ),
        focus=focus,
        projects=projects,
        experiments=experiments,
        workflows=workflows,
        recent_runs=recent_runs,
        failed_runs=failed_runs,
        running_runs=running_runs,
        assets=assets,
        stale_or_missing=flags,
    )


__all__ = [
    "ContextAsset",
    "ContextFocus",
    "ExperimentRef",
    "HealthFlag",
    "HealthFlagKind",
    "ProjectRef",
    "RunRef",
    "WorkflowRef",
    "WorkspaceContext",
    "WorkspaceRef",
    "assemble_workspace_context",
]
