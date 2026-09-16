"""Derived, in-memory read views over a workspace — the server's list model.

Why it exists
=============
Answering "list every run" from the entity tree costs ``O(N)`` file reads:
``Experiment.list_runs`` opens each ``run.json`` and every response field then
consults ``_ops/run.json``. :class:`~molexp.fs.memo.StatMemo` (P1) turned the
repeat reads into one ``stat`` each, but a poll still pays ``2N`` stats *and*
rebuilds every response row.

This module hoists that work into **snapshots**: a :class:`RunsSnapshot` is
built once, reused while the underlying files are unchanged, and rebuilt
incrementally — only the runs whose ``(size, mtime)`` key moved are re-read,
every other row is carried over *by reference*. A caller (the server's list
routes, via :mod:`molexp.services.workspace_read_model`) then serves a warm
list with zero file reads, and an unchanged snapshot's ``version`` is a
perfect ETag.

Law check (CLAUDE.md "One source of truth")
===========================================
Nothing here is persisted. Snapshots live in process memory, every row is
validated against the authoritative file's ``stat`` before it is reused, and
the authoritative files (``run.json`` / ``_ops/run.json`` / ``assets.json`` /
``meta.yaml``) remain the only truth. This is emphatically **not** the retired
derived asset index: there is no second on-disk copy to keep in sync, and a
process restart rebuilds from the authoritative tree.

Layer: pure ``workspace`` — imports ``workspace`` + ``knowledge`` + stdlib /
pydantic only, never ``services`` / ``server`` (the runtime container, its
refresh thread and the change bus all live one layer up).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from molexp._typing import JSONValue

from .models import ErrorInfo, ExecutionRecord, RunStatus
from .run_ops import RUN_OPS_NAME
from .workspace_context import ExperimentRef, ProjectRef, WorkflowRef

if TYPE_CHECKING:
    from molexp.fs.base import FileSystem
    from molexp.knowledge.bundle import Bundle
    from molexp.knowledge.bundle_index import BundleIndex
    from molexp.knowledge.concepts import Note, ReferenceConcept
    from molexp.knowledge.knowledge_item import KnowledgeItem
    from molexp.knowledge.retrieval import Bm25fCorpus

    from .experiment import Experiment
    from .project import Project
    from .run import Run
    from .workspace import Workspace

__all__ = [
    "KnowledgeSnapshot",
    "RunRow",
    "RunsSnapshot",
    "StatKey",
    "build_knowledge_snapshot",
    "build_runs_snapshot",
    "rows_changed",
    "stat_key",
]

#: A file's change-detection key — ``(size, mtime)``, or ``None`` when absent.
StatKey = tuple[int, float] | None

# Aware-UTC floor for rows carrying no timestamp (they sort last).
_TS_FLOOR = datetime(1970, 1, 1, tzinfo=UTC)

# Fields that change constantly on a *live* run without changing what any
# reader renders — a heartbeat re-stamp must not bump the snapshot version,
# or a running workspace would invalidate every ETag every 30 seconds.
_VOLATILE_FIELDS: set[str] = {"heartbeat_at"}


def stat_key(fs: FileSystem, path: str) -> StatKey:
    """``(size, mtime)`` of *path*, or ``None`` when it is absent/unreadable."""
    try:
        st = fs.stat(path)
    except Exception:  # absent, unreadable, or a transport hiccup
        return None
    return (st.size, st.mtime)


# ── Run rows ────────────────────────────────────────────────────────────────


class RunRow(BaseModel, frozen=True):
    """One run, flattened — everything the list surfaces render from.

    Carries the identity/provenance of ``run.json`` *and* the hot state of
    ``_ops/run.json`` in one immutable value, plus the two parent fields
    (``project_name`` / ``experiment_name``) and the experiment-level
    ``workflow_source`` / ``git_commit`` a run response echoes. Building one
    is the only place a snapshot touches those files; every response model
    then maps from the row without further I/O.
    """

    run_id: str
    project_id: str
    project_name: str
    experiment_id: str
    experiment_name: str

    status: str = RunStatus.PENDING.value
    is_retryable: bool = False
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    current_execution_id: str | None = None
    executions: tuple[ExecutionRecord, ...] = ()

    parameters: dict[str, JSONValue] = Field(default_factory=dict)
    config: dict[str, JSONValue] = Field(default_factory=dict)
    config_hash: str | None = None
    target: str | None = None
    profile: str | None = None
    executor_info: dict[str, JSONValue] = Field(default_factory=dict)
    error: ErrorInfo | None = None
    workflow_snapshot: dict[str, JSONValue] | None = None
    workflow_source: str | None = None
    git_commit: str | None = None
    context_results: dict[str, JSONValue] = Field(default_factory=dict)

    @property
    def sort_key(self) -> datetime:
        """``created_at`` as aware-UTC — the list ordering key (desc)."""
        ts = self.created_at
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def rows_changed(a: RunRow, b: RunRow) -> bool:
    """Whether two rows differ in anything a reader would see.

    :data:`_VOLATILE_FIELDS` (the heartbeat) is excluded on purpose: a live
    run re-stamps it every 30 s, and bumping the snapshot version for that
    would defeat every conditional request while anything is running.
    """
    return a.model_dump(exclude=_VOLATILE_FIELDS) != b.model_dump(exclude=_VOLATILE_FIELDS)


def _build_row(run: Run, project: Project, experiment: Experiment) -> RunRow:
    """Read one run into a :class:`RunRow` (memoized reads; ≤2 files)."""
    ops = run.read_ops()
    meta = run.metadata
    return RunRow(
        run_id=run.id,
        project_id=project.id,
        project_name=project.name,
        experiment_id=experiment.id,
        experiment_name=experiment.name,
        status=ops.status.value,
        is_retryable=ops.is_retryable,
        created_at=meta.created_at,
        started_at=ops.started_at,
        finished_at=ops.finished_at,
        heartbeat_at=ops.heartbeat_at,
        current_execution_id=ops.current_execution_id,
        executions=tuple(ops.executions),
        parameters=dict(meta.parameters),
        config=dict(meta.config),
        config_hash=meta.config_hash,
        target=meta.target,
        profile=meta.profile,
        executor_info=dict(meta.executor_info or {}),
        error=meta.error,
        workflow_snapshot=meta.workflow_snapshot,
        workflow_source=experiment.metadata.workflow_source,
        git_commit=experiment.metadata.git_commit,
        context_results=run.context_results,
    )


_RUNNING_STATES = frozenset({"running"})
_PENDING_STATES = frozenset({"pending", "queued", "submitted", "created"})
_FAILED_STATES = frozenset({"failed", "timed_out", "cancelled", "lost"})
_SUCCEEDED_STATES = frozenset({"succeeded"})


def _stats_of(rows: tuple[RunRow, ...]) -> dict[str, int]:
    stats = {"total": len(rows), "running": 0, "pending": 0, "failed": 0, "succeeded": 0}
    for row in rows:
        state = row.status.lower()
        if state in _RUNNING_STATES:
            stats["running"] += 1
        elif state in _PENDING_STATES:
            stats["pending"] += 1
        elif state in _FAILED_STATES:
            stats["failed"] += 1
        elif state in _SUCCEEDED_STATES:
            stats["succeeded"] += 1
    return stats


class RunsSnapshot:
    """An immutable-by-convention view of every run in a workspace.

    A plain class, not a pydantic model: it holds derived dict indexes and is
    handed around by reference, never validated or serialized.

    Attributes:
        version: Bumped only when some row actually changed (see
            :func:`rows_changed`) — the ETag source.
        rows: Every run, ``created_at`` descending.
        by_id / by_experiment: Lookup indexes over :attr:`rows`.
        experiment_version: Per-``(project, experiment)`` version, so an
            experiment's run list gets its own ETag and a change in one
            experiment does not invalidate the others.
        projects / experiments / workflows: The structural refs read during
            the same walk (a context assembly needs no second one).
        stats: Status histogram over :attr:`rows`.
        last_seq: The event-spine ``seq`` this snapshot was built at.
    """

    __slots__ = (
        "_container_keys",
        "_keys",
        "built_at",
        "by_experiment",
        "by_id",
        "experiment_version",
        "experiments",
        "last_seq",
        "projects",
        "rows",
        "stats",
        "version",
        "workflows",
    )

    def __init__(
        self,
        *,
        version: int,
        rows: tuple[RunRow, ...],
        projects: tuple[ProjectRef, ...] = (),
        experiments: tuple[ExperimentRef, ...] = (),
        workflows: tuple[WorkflowRef, ...] = (),
        experiment_version: dict[tuple[str, str], int] | None = None,
        keys: dict[str, tuple[StatKey, StatKey]] | None = None,
        container_keys: dict[str, StatKey] | None = None,
        last_seq: int = 0,
        built_at: float | None = None,
    ) -> None:
        import time

        self.version = version
        self.rows = rows
        self.projects = projects
        self.experiments = experiments
        self.workflows = workflows
        self.by_id: dict[str, RunRow] = {r.run_id: r for r in rows}
        by_exp: dict[tuple[str, str], list[RunRow]] = {}
        for row in rows:
            by_exp.setdefault((row.project_id, row.experiment_id), []).append(row)
        self.by_experiment: dict[tuple[str, str], tuple[RunRow, ...]] = {
            k: tuple(v) for k, v in by_exp.items()
        }
        self.experiment_version = experiment_version or dict.fromkeys(self.by_experiment, version)
        self.stats = _stats_of(rows)
        self._keys = keys or {}
        self._container_keys = container_keys or {}
        self.last_seq = last_seq
        self.built_at = built_at if built_at is not None else time.monotonic()

    def experiment_rows(self, project_id: str, experiment_id: str) -> tuple[RunRow, ...]:
        """Rows of one experiment (``created_at`` desc), or ``()``."""
        return self.by_experiment.get((project_id, experiment_id), ())

    def version_for_experiment(self, project_id: str, experiment_id: str) -> int:
        """The per-experiment ETag version (falls back to the global one)."""
        return self.experiment_version.get((project_id, experiment_id), self.version)

    def __len__(self) -> int:
        return len(self.rows)


def _run_files(run: Run) -> tuple[str, str]:
    """``(run.json, _ops/run.json)`` paths of *run* — pure path math."""
    return (
        run.fs.join(run.resolve(), "run.json"),
        run._ops_json_path(RUN_OPS_NAME),
    )


def build_runs_snapshot(
    workspace: Workspace,
    *,
    previous: RunsSnapshot | None = None,
    last_seq: int = 0,
) -> RunsSnapshot:
    """Build (or incrementally rebuild) the runs view of *workspace*.

    Walks the authoritative tree once. With *previous*, each run's two files
    are ``stat``\\ ed and an unchanged pair carries the previous row over **by
    reference** — so an unchanged sweep does ``2N`` stats and **zero** reads,
    and the returned snapshot keeps ``previous.version`` when nothing a reader
    can see has changed.

    Args:
        workspace: The workspace to project.
        previous: The last snapshot, for incremental reuse.
        last_seq: Event-spine cursor to stamp on the result.

    Returns:
        A fresh :class:`RunsSnapshot` (possibly sharing rows with *previous*).
    """
    fs = workspace.fs
    rows: list[RunRow] = []
    keys: dict[str, tuple[StatKey, StatKey]] = {}
    container_keys: dict[str, StatKey] = {}
    projects: list[ProjectRef] = []
    experiments: list[ExperimentRef] = []
    workflows: list[WorkflowRef] = []
    changed = previous is None
    prev_keys = previous._keys if previous is not None else {}
    prev_by_id = previous.by_id if previous is not None else {}
    touched_experiments: set[tuple[str, str]] = set()

    projects_dir = fs.join(workspace.resolve(), "projects")
    container_keys[projects_dir] = stat_key(fs, projects_dir)
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
            if experiment.workflow_source is not None:
                workflows.append(WorkflowRef(experiment_id=experiment.id, name=experiment.name))
            runs_dir = fs.join(experiment.resolve(), "runs")
            container_keys[runs_dir] = stat_key(fs, runs_dir)
            # ``sync=False``: the stat below is the freshness check, so paying
            # ``sync_metadata``'s stat too would double the sweep cost.
            for run in experiment.list_runs(sync=False):
                run_json, ops_json = _run_files(run)
                key = (stat_key(fs, run_json), stat_key(fs, ops_json))
                keys[run.id] = key
                cached = prev_by_id.get(run.id)
                if cached is not None and prev_keys.get(run.id) == key:
                    rows.append(cached)
                    continue
                run.sync_metadata()
                row = _build_row(run, project, experiment)
                rows.append(row)
                if cached is None or rows_changed(cached, row):
                    changed = True
                    touched_experiments.add((project.id, experiment.id))

    rows.sort(key=lambda r: r.sort_key, reverse=True)
    frozen = tuple(rows)

    # Structure can still have changed (a run added *and* removed keeps
    # ``changed`` False above) — compare the id set before reusing.
    if previous is not None and not changed and set(previous.by_id) != set(keys):
        changed = True
        touched_experiments |= {(r.project_id, r.experiment_id) for r in frozen}
        touched_experiments |= {(r.project_id, r.experiment_id) for r in previous.rows}

    version = (previous.version if previous is not None else 0) + (1 if changed else 0)
    exp_version: dict[tuple[str, str], int] = {}
    prev_exp_version = previous.experiment_version if previous is not None else {}
    for row in frozen:
        pair = (row.project_id, row.experiment_id)
        if pair in touched_experiments or pair not in prev_exp_version:
            exp_version[pair] = version
        else:
            exp_version[pair] = prev_exp_version[pair]

    return RunsSnapshot(
        version=version,
        rows=frozen,
        projects=tuple(projects),
        experiments=tuple(experiments),
        workflows=tuple(workflows),
        experiment_version=exp_version,
        keys=keys,
        container_keys=container_keys,
        last_seq=last_seq,
    )


def runs_snapshot_is_stale(workspace: Workspace, snapshot: RunsSnapshot) -> bool:
    """Cheap structural probe: did a ``runs/`` container's mtime move?

    One ``stat`` per recorded container. Answers "was a run added or removed"
    without listing anything; per-run changes are caught by the key compare in
    :func:`build_runs_snapshot`.
    """
    fs = workspace.fs
    return any(stat_key(fs, path) != key for path, key in snapshot._container_keys.items())


# ── Knowledge ───────────────────────────────────────────────────────────────


class KnowledgeSnapshot:
    """The bundle index, bodies, metas and BM25F corpus of one walk.

    Built from :meth:`~molexp.knowledge.bundle.Bundle.scan_index` (a read —
    it never writes ``index.json`` / ``INDEX.md``) plus one
    :meth:`~molexp.knowledge.bundle.Bundle.partition` walk for the typed
    views. Ranking reuses the prebuilt corpus, so a search is no longer a
    full-tree rescan per keystroke.
    """

    __slots__ = (
        "_concept_keys",
        "bodies",
        "built_at",
        "corpus",
        "index",
        "items",
        "metas",
        "notes",
        "references",
        "version",
    )

    def __init__(
        self,
        *,
        version: int,
        index: BundleIndex,
        bodies: dict[str, str],
        metas: dict[str, dict[str, Any]],
        corpus: Bm25fCorpus | None = None,
        notes: tuple[Note, ...] = (),
        references: tuple[ReferenceConcept, ...] = (),
        items: tuple[KnowledgeItem, ...] = (),
        concept_keys: dict[str, tuple[StatKey, StatKey]] | None = None,
        built_at: float | None = None,
    ) -> None:
        import time

        self.version = version
        self.index = index
        self.bodies = bodies
        self.metas = metas
        self.corpus = corpus
        self.notes = notes
        self.references = references
        self.items = items
        self._concept_keys = concept_keys or {}
        self.built_at = built_at if built_at is not None else time.monotonic()

    def backlink_paths(self, rel_path: str) -> list[str]:
        """Bundle-relative paths of the Concepts whose ``index.md`` links *rel_path*.

        Inverts :attr:`index`'s forward edges — pure computation, no I/O.
        Paths only: :class:`~molexp.knowledge.bundle_index.ConceptIndexEntry`
        records link *targets*, not their
        :class:`~molexp.knowledge.edges.EdgeRole`, so a caller that needs the
        declared role still goes through
        :meth:`~molexp.knowledge.bundle.Bundle.backlinks` (whose walk is
        layout-pruned since P1).
        """
        target = rel_path.rstrip("/")
        return [
            entry.path
            for entry in self.index.entries
            if entry.path.rstrip("/") != target
            and any(str(link).rstrip("/") == target for link in entry.links)
        ]


def _concept_files(bundle: Bundle, rel: str) -> tuple[str, str]:
    fs = bundle.fs
    base = fs.join(str(bundle.root), rel) if rel not in {"", "."} else str(bundle.root)
    return fs.join(base, "meta.yaml"), fs.join(base, "index.md")


def build_knowledge_snapshot(
    workspace: Workspace,
    *,
    previous: KnowledgeSnapshot | None = None,
) -> KnowledgeSnapshot:
    """Scan the workspace bundle into a :class:`KnowledgeSnapshot` (never writes).

    The walk is the layout-pruned workspace :class:`~molexp.workspace.bundle.Bundle`,
    so run-internal directories (``executions/`` / ``artifacts/`` / …) are
    never descended into.
    """
    from .bundle import Bundle

    bundle = Bundle(workspace.resolve())
    # ONE walk for the index, the bodies, the markers and the typed views —
    # ``scan_index`` + ``partition`` would walk the tree twice.
    scan = bundle.scan_all()
    keys = {rel: _stat_pair(bundle, rel) for rel in scan.metas}

    version = (previous.version if previous is not None else 0) + 1
    if previous is not None and previous._concept_keys == keys:
        version = previous.version

    return KnowledgeSnapshot(
        version=version,
        index=scan.index,
        bodies=scan.bodies,
        metas=dict(scan.metas),
        corpus=bundle.ranking_corpus(scan.index, scan.bodies),
        notes=tuple(scan.notes),
        references=tuple(scan.references),
        items=tuple(scan.items),
        concept_keys=keys,
    )


def _stat_pair(bundle: Bundle, rel: str) -> tuple[StatKey, StatKey]:
    meta_path, index_path = _concept_files(bundle, rel)
    return stat_key(bundle.fs, meta_path), stat_key(bundle.fs, index_path)


def knowledge_snapshot_is_stale(workspace: Workspace, snapshot: KnowledgeSnapshot) -> bool:
    """One ``stat`` per known Concept file — did any ``meta.yaml`` / ``index.md`` move?

    Does **not** detect a brand-new Concept directory (that needs a walk); the
    refresher pairs this with a periodic full sweep and with the
    ``knowledge.created`` event-spine signal.
    """
    from .bundle import Bundle

    bundle = Bundle(workspace.resolve())
    return any(_stat_pair(bundle, rel) != key for rel, key in snapshot._concept_keys.items())
