"""``WorkspaceContext`` — the canonical workspace read-model + its assembler.

`WorkspaceContext` is the single structured projection the system hands to agents,
planners, the server, the CLI, and the UI so they reason over one shape instead of
re-assembling workspace state three ways. It is slice 01 of the P0.2 "WorkspaceContext
— full unification" chain (`.claude/notes/integration.md` §1).

Design invariants:

- **Pure projection.** :func:`assemble_workspace_context` is a read — it stores nothing
  new and the model is never itself canonical (authoritative state stays in the entity
  ``*.json`` / ``_ops/run.json`` / ``assets.json`` / OKF ``meta.yaml``).
- **Layer-legal.** This module imports only ``workspace`` + stdlib/pydantic — never
  ``workflow`` / ``agent`` / ``harness`` (enforced by the workspace import-guard). Workflow
  *availability* is read workspace-only from the externalized ``workflow.json``.
- **Focus is caller-supplied.** :class:`ContextFocus` (active project/experiment/run +
  selected refs) is passed in, never persisted; it defaults to empty.
- **Health flags are computed, never stored** — and only the workspace-computable subset
  is produced here (``failed_run`` / ``stale_running`` / ``orphan_artifact``).
  ``missing_output`` (needs the harness ``WorkflowIR``) and ``stale_knowledge`` + a
  populated ``open_questions`` (need the typed ``KnowledgeItem`` / ``SourceRef`` of P0.4)
  are computed one layer up later; ``open_questions`` is ``[]`` here by design.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path as _StdPath
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from molexp._typing import JSONValue

from .assets.scan import scan_assets
from .bundle import Bundle
from .bundle_index import extract_title
from .concepts import Note, ReferenceConcept
from .knowledge_item import KnowledgeItem
from .models import RunStatus

if TYPE_CHECKING:
    from .assets.scan import AssetScanSnapshot
    from .read_model import KnowledgeSnapshot, RunsSnapshot
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
    """A run's identity + hot-state summary (from ``_ops/run.json``)."""

    run_id: str
    experiment_id: str
    project_id: str
    status: str
    config_hash: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    current_execution_id: str | None = None


class ArtifactRef(BaseModel, frozen=True):
    """An asset + its producer lineage (from the manifest scan)."""

    asset_id: str
    scope: str
    kind: str
    path: str
    content_hash: str | None = None
    run_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None


class KnowledgeRef(BaseModel, frozen=True):
    """A knowledge Concept's identity (bundle-relative path + type + title)."""

    path: str
    type: str
    title: str
    id: str | None = None


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
    artifacts: list[ArtifactRef] = []
    knowledge: list[KnowledgeRef] = []
    open_questions: list[KnowledgeRef] = []
    stale_or_missing: list[HealthFlag] = []


def _run_sort_key(ref: RunRef) -> tuple[datetime, str]:
    ts = ref.finished_at or ref.started_at or _TS_FLOOR
    # Persisted run timestamps may be offset-naive (older writers); a mixed
    # naive/aware set must still sort. Naive values are treated as UTC.
    aware = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    # ``run_id`` breaks ties explicitly: runs that never started all carry the
    # same floor timestamp, and without this their order would depend on the
    # order the caller happened to supply them in — which differs between the
    # reading assembly (directory order) and the snapshot one (created_at).
    return (aware, ref.run_id)


def assemble_workspace_context(
    workspace: Workspace,
    *,
    focus: ContextFocus | None = None,
    now: datetime | None = None,
    runs: RunsSnapshot | None = None,
    assets: AssetScanSnapshot | None = None,
    knowledge: KnowledgeSnapshot | None = None,
) -> WorkspaceContext:
    """Assemble the canonical :class:`WorkspaceContext` — a pure read.

    Walks the authoritative folder tree + ``read_ops`` + ``scan_assets`` + ``Bundle`` and
    composes them into one read-model. Writes nothing.

    Args:
        workspace: The workspace to project.
        focus: Caller-supplied ephemeral focus (default: empty); echoed, never stored.
        now: Reference time for heartbeat-staleness (default: aware-UTC now); injected for
            deterministic tests.
        runs: A prebuilt :class:`~molexp.workspace.read_model.RunsSnapshot`.
        assets: A prebuilt
            :class:`~molexp.workspace.assets.scan.AssetScanSnapshot`.
        knowledge: A prebuilt
            :class:`~molexp.workspace.read_model.KnowledgeSnapshot`.

    Pass all three snapshots (the server does, from its read model) and the
    assembly does **zero** file I/O — it is then pure composition over data
    already in memory. Omit them and each section is read from disk exactly as
    before, which is what the CLI and every direct caller still do.

    Returns:
        The assembled :class:`WorkspaceContext`.
    """
    focus = focus if focus is not None else ContextFocus()
    now = now if now is not None else datetime.now(UTC)
    root = str(workspace.resolve())
    if runs is not None and assets is not None and knowledge is not None:
        return _context_from_snapshots(
            workspace, focus=focus, now=now, runs=runs, assets=assets, knowledge=knowledge
        )

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
            # A freshly-loaded Experiment rehydrates workflow_source from workflow.json
            # (experiment.from_disk), so this covers both embedded + externalized IRs.
            if experiment.workflow_source is not None:
                workflows.append(WorkflowRef(experiment_id=experiment.id, name=experiment.name))
            for run in experiment.list_runs():
                ops = run.read_ops()
                err = run.metadata.error
                err_text = f"{err.type}: {err.message}" if err is not None else None
                ref = RunRef(
                    run_id=run.id,
                    experiment_id=experiment.id,
                    project_id=project.id,
                    status=str(ops.status),
                    config_hash=run.metadata.config_hash,
                    started_at=ops.started_at,
                    finished_at=ops.finished_at,
                    current_execution_id=ops.current_execution_id,
                )
                run_refs.append(ref)
                run_ids.add(run.id)
                if ops.is_retryable:  # same parse as above — no second sidecar read
                    failed_runs.append(ref)
                    # Say WHY, not just that it failed — the captured error is the
                    # one signal a user needs to act (integration.md §1.4 "no
                    # silent invalid state").
                    reason = f": {err_text}" if err_text else ""
                    flags.append(
                        HealthFlag(
                            kind="failed_run",
                            ref=run.id,
                            detail=f"run {run.id} is {ops.status} (retryable){reason}",
                        )
                    )
                if ops.status == RunStatus.RUNNING:
                    running_runs.append(ref)
                    if ops.is_heartbeat_stale(now):
                        flags.append(
                            HealthFlag(
                                kind="stale_running",
                                ref=run.id,
                                detail=f"run {run.id} is running but its heartbeat is stale",
                            )
                        )

    recent_runs = sorted(run_refs, key=_run_sort_key, reverse=True)

    artifacts: list[ArtifactRef] = []
    for asset in scan_assets(root):
        producer = asset.producer
        artifacts.append(
            ArtifactRef(
                asset_id=asset.asset_id,
                scope=asset.scope.urn,
                kind=str(getattr(asset, "kind", "")),
                path=str(asset.path),
                content_hash=asset.content_hash,
                run_id=producer.run_id if producer else None,
                execution_id=producer.execution_id if producer else None,
                task_id=producer.task_id if producer else None,
            )
        )
        if producer and producer.run_id and producer.run_id not in run_ids:
            flags.append(
                HealthFlag(
                    kind="orphan_artifact",
                    ref=asset.asset_id,
                    detail=(
                        f"asset {asset.asset_id} names producer run "
                        f"{producer.run_id!r}, which no longer resolves"
                    ),
                )
            )

    knowledge: list[KnowledgeRef] = []
    bundle = Bundle(root)
    # ``walk_with_meta`` hands back the ``meta.yaml`` the walk already parsed
    # to decide each dir's type — one read per Concept, never a second.
    for concept, meta in bundle.walk_with_meta():
        # Knowledge is the free-form Note, the literature ReferenceConcept, and the
        # typed source-attributed KnowledgeItem (P0.4) — the canonical home for
        # auto-derived knowledge. Entity folders (Project/Experiment/Run) are excluded.
        if isinstance(concept, Note | ReferenceConcept | KnowledgeItem):
            raw_id = meta.get("id")
            knowledge.append(
                KnowledgeRef(
                    path=bundle.rel_path(concept),
                    type=str(meta.get("type", "")),
                    title=extract_title(concept.read_index()) or concept.name,
                    id=str(raw_id) if raw_id is not None else None,
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
        knowledge=knowledge,
        open_questions=[],
        stale_or_missing=flags,
    )


def _artifact_refs(assets: AssetScanSnapshot) -> list[ArtifactRef]:
    out: list[ArtifactRef] = []
    for asset in assets.assets:
        producer = asset.producer
        out.append(
            ArtifactRef(
                asset_id=asset.asset_id,
                scope=asset.scope.urn,
                kind=str(getattr(asset, "kind", "")),
                path=str(asset.path),
                content_hash=asset.content_hash,
                run_id=producer.run_id if producer else None,
                execution_id=producer.execution_id if producer else None,
                task_id=producer.task_id if producer else None,
            )
        )
    return out


def _context_from_snapshots(
    workspace: Workspace,
    *,
    focus: ContextFocus,
    now: datetime,
    runs: RunsSnapshot,
    assets: AssetScanSnapshot,
    knowledge: KnowledgeSnapshot,
) -> WorkspaceContext:
    """The zero-I/O assembly path — pure composition over prebuilt snapshots.

    Kept beside the reading path on purpose: a parity test asserts the two
    produce equal contexts for the same workspace, so this can never silently
    drift into a different projection.
    """
    from molexp.knowledge.bundle_index import extract_title

    from .run_ops import HEARTBEAT_STALE_SECONDS

    run_refs: list[RunRef] = []
    failed_runs: list[RunRef] = []
    running_runs: list[RunRef] = []
    flags: list[HealthFlag] = []
    run_ids: set[str] = set()

    for row in runs.rows:
        ref = RunRef(
            run_id=row.run_id,
            experiment_id=row.experiment_id,
            project_id=row.project_id,
            status=row.status,
            config_hash=row.config_hash,
            started_at=row.started_at,
            finished_at=row.finished_at,
            current_execution_id=row.current_execution_id,
        )
        run_refs.append(ref)
        run_ids.add(row.run_id)
        if row.is_retryable:
            failed_runs.append(ref)
            reason = f": {row.error.type}: {row.error.message}" if row.error is not None else ""
            flags.append(
                HealthFlag(
                    kind="failed_run",
                    ref=row.run_id,
                    detail=f"run {row.run_id} is {row.status} (retryable){reason}",
                )
            )
        if row.status == RunStatus.RUNNING.value:
            running_runs.append(ref)
            beat = row.heartbeat_at
            if beat is not None:
                aged = beat if beat.tzinfo is not None else beat.replace(tzinfo=UTC)
                if (now - aged).total_seconds() > HEARTBEAT_STALE_SECONDS:
                    flags.append(
                        HealthFlag(
                            kind="stale_running",
                            ref=row.run_id,
                            detail=f"run {row.run_id} is running but its heartbeat is stale",
                        )
                    )

    artifacts = _artifact_refs(assets)
    for artifact in artifacts:
        if artifact.run_id and artifact.run_id not in run_ids:
            flags.append(
                HealthFlag(
                    kind="orphan_artifact",
                    ref=artifact.asset_id,
                    detail=(
                        f"asset {artifact.asset_id} names producer run "
                        f"{artifact.run_id!r}, which no longer resolves"
                    ),
                )
            )

    knowledge_refs: list[KnowledgeRef] = []
    for concept in (*knowledge.notes, *knowledge.references, *knowledge.items):
        rel = _StdPath(str(concept.path)).relative_to(_StdPath(root_of(workspace))).as_posix()
        meta = knowledge.metas.get(rel, {})
        raw_id = meta.get("id")
        knowledge_refs.append(
            KnowledgeRef(
                path=rel,
                type=str(meta.get("type", "")),
                title=extract_title(knowledge.bodies.get(rel, "")) or concept.name,
                id=str(raw_id) if raw_id is not None else None,
            )
        )

    return WorkspaceContext(
        workspace=WorkspaceRef(
            id=workspace.id,
            name=workspace.name,
            root=root_of(workspace),
            targets=[t.name for t in workspace.metadata.targets],
        ),
        focus=focus,
        projects=list(runs.projects),
        experiments=list(runs.experiments),
        workflows=list(runs.workflows),
        recent_runs=sorted(run_refs, key=_run_sort_key, reverse=True),
        failed_runs=failed_runs,
        running_runs=running_runs,
        artifacts=artifacts,
        knowledge=knowledge_refs,
        open_questions=[],
        stale_or_missing=flags,
    )


def root_of(workspace: Workspace) -> str:
    """The workspace root as a string (one place, so both paths agree)."""
    return str(workspace.resolve())


__all__ = [
    "ArtifactRef",
    "ContextFocus",
    "ExperimentRef",
    "HealthFlag",
    "HealthFlagKind",
    "KnowledgeRef",
    "ProjectRef",
    "RunRef",
    "WorkflowRef",
    "WorkspaceContext",
    "WorkspaceRef",
    "assemble_workspace_context",
]
