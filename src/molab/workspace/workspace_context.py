"""``WorkspaceContext`` — the canonical workspace read-model + its assembler.

`WorkspaceContext` is the single structured projection the system hands to agents,
planners, the server, the CLI, and the UI so they reason over one shape instead of
re-assembling workspace state three ways. It is slice 01 of the P0.2 "WorkspaceContext
— full unification" chain (`.claude/notes/integration.md` §1).

Design invariants:

- **Pure projection.** :func:`assemble_workspace_context` is a read — it stores nothing
  new and the model is never itself canonical (authoritative state stays in the entity
  ``*.json`` / OKF ``meta.json``).
- **Layer-legal.** This module imports only ``workspace`` + stdlib/pydantic — never
  upstream layers (enforced by the workspace import-guard). Workflow
  *availability* is read workspace-only from the externalized ``workflow.json``.
- **Focus is caller-supplied.** :class:`ContextFocus` (active project/experiment/run +
  selected refs) is passed in, never persisted; it defaults to empty.
- **Health flags are computed, never stored** — and only the workspace-computable subset
  is produced here (``failed_run`` / ``stale_running`` / ``orphan_artifact``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from molab._typing import JSONValue

from .run_heartbeat import is_alive_stale

if TYPE_CHECKING:
    from .workspace import Workspace

# Aware-UTC floor for ordering runs that carry no timestamp (they sort last).
_TS_FLOOR = datetime(1970, 1, 1, tzinfo=UTC)

HealthFlagKind = Literal["failed_run", "stale_running", "orphan_artifact"]


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
    """A run's identity + hot-state summary (from ``run.json``)."""

    run_id: str
    experiment_id: str
    project_id: str
    status: str
    config_hash: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    current_execution_id: str | None = None


class ContextArtifact(BaseModel, frozen=True):
    """One emitted Artifact in the workspace read-model.

    ``path`` is workspace-relative and comes from ``walk_artifacts`` (the
    same location ``ArtifactRepository.locate`` returns). This is not
    :class:`molab.workspace.domain.ArtifactRef`, which is only an id pointer.
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
    artifacts: list[ContextArtifact] = []
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

    Walks the authoritative folder tree + ``run.json`` and
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

    for project in workspace.list_projects():
        projects.append(ProjectRef(id=project.id, name=project.name))
        for experiment in project.list_experiments():
            experiments.append(
                ExperimentRef(
                    id=experiment.id,
                    name=experiment.name,
                    project_id=project.id,
                    parameter_space=dict(experiment.parameter_space),
                )
            )
            if experiment.workflow_kind is not None:
                workflows.append(WorkflowRef(experiment_id=experiment.id, name=experiment.name))
            for run in experiment.list_runs():
                executions = run.executions
                latest = executions[-1] if executions else None
                err = latest.error if latest else None
                err_text = (
                    f"{err.get('type', 'Error')}: {err.get('message', '')}"
                    if err is not None
                    else None
                )
                status = run.status_label
                started = min(
                    (e.started_at for e in executions if e.started_at is not None),
                    default=None,
                )
                ref = RunRef(
                    run_id=run.id,
                    experiment_id=experiment.id,
                    project_id=project.id,
                    status=status,
                    config_hash=run.metadata.definition_hash,
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

    artifacts: list[ContextArtifact] = []
    # Emitted products, read from the Executions that own them.
    from .artifact_repository import walk_artifacts

    root_path = Path(root).resolve()
    for located in walk_artifacts(workspace):
        art = located.artifact
        task_id = art.metadata.get("task_id") if isinstance(art.metadata, dict) else None
        relative = ""
        if located.location is not None:
            try:
                relative = Path(located.location).resolve().relative_to(root_path).as_posix()
            except ValueError:
                relative = ""
        artifacts.append(
            ContextArtifact(
                asset_id=art.id,
                scope=f"artifact:{art.project_id}:{art.run_id}:{art.execution_id}",
                kind=art.semantic_type or "artifact",
                path=relative,
                content_hash=art.content.digest,
                run_id=art.run_id,
                execution_id=art.execution_id,
                task_id=str(task_id) if task_id is not None else None,
            )
        )
        if art.run_id not in run_ids:
            flags.append(
                HealthFlag(
                    kind="orphan_artifact",
                    ref=art.id,
                    detail=(
                        f"artifact {art.id} names producer run "
                        f"{art.run_id!r}, which no longer resolves"
                    ),
                )
            )

    return WorkspaceContext(
        workspace=WorkspaceRef(
            id=workspace.id,
            name=workspace.name,
            root=root,
            targets=[t.name for t in workspace.metadata.targets],
        ),
        focus=focus,
        projects=projects,
        experiments=experiments,
        workflows=workflows,
        recent_runs=recent_runs,
        failed_runs=failed_runs,
        running_runs=running_runs,
        artifacts=artifacts,
        stale_or_missing=flags,
    )


__all__ = [
    "ContextArtifact",
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
