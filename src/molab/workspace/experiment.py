"""Experiment entity — one directory per parameter combination.

Inherits :class:`Folder` (sub-spec 02) so it participates in the
unified workspace folder abstraction: ``kind`` is
:data:`WORKSPACE_EXPERIMENT_KIND`, ``parent`` is the owning
:class:`Project`.

An Experiment is a parameter-space container plus replica configuration
(``n_replicas`` × ``seeds``). Replicas under the same Experiment share
parameters; they differ only in their random seed.

Workspace does **not** import the workflow layer (hard layer-DAG invariant).
Pairing an Experiment with a workflow goes through the :class:`WorkflowExecutor`
inversion seam, so the fluent ``exp.run(workflow, params=...)`` reads cleanly
without workspace ever importing ``molab.workflow``:

    >>> exp = ws.project("demo").experiment("series")
    >>> exp.run(build_workflow(), params={"lr": [1e-3, 1e-4]})

``params`` is the sweep (the per-run **inputs**); it is expanded into one
content-addressed Run per cell, and ``molab run`` drives execution.

Construction is side-effect free; ``project.add_experiment(...)``
materializes on disk at call-time (idempotent: if an experiment with
the same slug already exists, it is loaded and returned).
"""  # noqa: RUF002

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from molab.param import ParamSpace

    from .artifact_repository import AssetRepository
    from .project import Project
    from .runset import RunSet
    from .workspace import Workspace

from molab._typing import JSONValue
from molab.ids import compute_definition_hash, generate_uuid7
from molab.path import Path

from .base import (
    _load_metadata,
    _reconstruct,
    _save_metadata,
)
from .domain import AssetScope
from .errors import ExperimentExistsError, ExperimentNotFoundError
from .folder import (
    WORKSPACE_EXPERIMENT_KIND,
    WORKSPACE_RUN_KIND,
    Folder,
    _validate_target_registered,
    register_entity_class,
)
from .fs import PathArg
from .models import ExperimentMetadata, FolderMetadata, WorkflowKind
from .naming import EXPERIMENT_CONTAINER, RUN_CONTAINER, disambiguate, entity_slug, run_slug
from .run import Run, compute_run_definition_hash

# Default replica seeds — deterministic, well-separated
_DEFAULT_SEEDS = [42, 123, 456, 789, 1234]


class WorkflowExecutor(Protocol):
    """Cross-layer seam: associate a workflow with an experiment for execution.

    The workspace layer MUST NOT import the workflow layer (hard layer-DAG
    invariant). This Protocol is the inversion seam: the orchestration layer
    implements it and registers it via :func:`set_workflow_executor`, so
    :meth:`Experiment.run` reads fluently — ``exp.run(workflow, ...)`` —
    without workspace ever importing ``molab.workflow``. (Same pattern as
    :func:`molab.workspace.run.set_run_executor`.)
    """

    def __call__(self, experiment: Experiment, workflow: object) -> None: ...


_workflow_executor: WorkflowExecutor | None = None


def set_workflow_executor(executor: WorkflowExecutor) -> None:
    """Register the implementation backing :meth:`Experiment.run`.

    Called once by the orchestration layer at ``import molab`` time (see
    :mod:`molab.entry`). Until then, :meth:`Experiment.run` fails fast.
    """
    global _workflow_executor
    _workflow_executor = executor


# Standalone home for a compiled workflow IR document, written alongside
# ``experiment.json``. Kept separate (and free of the ``schema_version``
# envelope) so external tooling — notably the molab VSCode preview — can read
# and diff the raw IR directly without parsing it out of the metadata file.
WORKFLOW_DOC_FILENAME = "workflow.ir.json"

#: Sentinel: the caller did not pass a document, so read the current file.
_CURRENT = object()


def _experiment_definition_hash(
    values: Mapping[str, object],
    *,
    document: dict[str, JSONValue] | None,
) -> str:
    """Content digest of an experiment definition.

    Eight keys. A document binding contributes *document*; a code binding and
    an unbound experiment contribute ``None``. The locator is not an input.

    Args:
        values: Experiment metadata fields. ``workflow_kind`` selects whether
            *document* is folded in.
        document: The IR to fold when ``workflow_kind`` is ``"document"``.
    """
    folded = document if values.get("workflow_kind") == "document" else None
    return compute_definition_hash(
        {
            "name": values.get("name"),
            "description": values.get("description"),
            "tags": values.get("tags"),
            "parameter_space": values.get("parameter_space"),
            "n_replicas": values.get("n_replicas"),
            "seeds": values.get("seeds"),
            "default_target": values.get("default_target"),
            "workflow_document": folded,
        }
    )


@register_entity_class
class Experiment(Folder):
    """Repeatable experiment — a parameter-space container.

    Example::

        exp = project.add_experiment(
            "lr-1e-3",
            params={"lr": 1e-3},
            n_replicas=3,
        )
        run = exp.add_run()
        # Workflow execution is the caller's concern; workspace just
        # provides the Run that workflow.execute(run=...) operates on.
    """

    _exists_error_cls = ExperimentExistsError
    _not_found_error_cls = ExperimentNotFoundError

    def __init__(
        self,
        *,
        parent: Project | None = None,
        name: str,
        kind: str = WORKSPACE_EXPERIMENT_KIND,
        project: Project | None = None,
        id: str | None = None,
        params: dict[str, JSONValue] | None = None,
        n_replicas: int = 1,
        seeds: list[int] | None = None,
        description: str = "",
        tags: list[str] | None = None,
        target: str | None = None,
        _entity_metadata: ExperimentMetadata | None = None,
    ) -> None:
        resolved_parent = parent if parent is not None else project
        if resolved_parent is None:
            raise ValueError("Experiment: parent (or project) is required")

        meta = (
            _entity_metadata
            if _entity_metadata is not None
            else ExperimentMetadata(
                id=id if id is not None else generate_uuid7(),
                name=name,
                description=description,
                tags=list(tags) if tags is not None else [],
                parameter_space=dict(params) if params else {},
                n_replicas=n_replicas,
                seeds=list(seeds) if seeds is not None else None,
                default_target=target,
                revision_id=generate_uuid7(),
                definition_hash=_experiment_definition_hash(
                    {
                        "name": name,
                        "description": description,
                        "tags": list(tags) if tags is not None else [],
                        "parameter_space": dict(params) if params else {},
                        "n_replicas": n_replicas,
                        "seeds": list(seeds) if seeds is not None else None,
                        "default_target": target,
                        "workflow_kind": None,
                    },
                    document=None,
                ),
            )
        )
        self._staged_document: dict[str, JSONValue] | None = None

        self._parent = resolved_parent
        self._name = entity_slug(meta.name, fallback=meta.id)
        self._kind = kind
        self._root_path = None
        # Disk is resolved via the parent chain (:meth:`Folder._disk`).
        self._metadata = FolderMetadata(
            id=meta.id,
            name=meta.name,
            kind=kind,
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )
        self._children_cache = {}

        # Entity-specific state
        self._entity_metadata: ExperimentMetadata = meta

    # ── Folder hooks ─────────────────────────────────────────────────────

    def resolve(self) -> Path:
        return self.experiment_dir

    @classmethod
    def child_dir(cls, parent: Folder, derived_id: str) -> Path:
        """Folder hook — experiments live under ``experiments/<id>/``."""
        # resolve() not path() — pure layout math must not mkdir on remote.
        return Path(parent._disk().join(parent.resolve(), EXPERIMENT_CONTAINER, derived_id))

    @classmethod
    def from_disk(cls, child_dir: PathArg, parent: Folder) -> Experiment:
        """Load ``experiment.json`` and rebuild entity state.

        ``workflow.ir.json`` stays on disk. :attr:`workflow_document` reads it;
        this loader does not copy it into metadata.
        """
        meta = _load_metadata(
            ExperimentMetadata, parent._disk().join(child_dir, "experiment.json"), fs=parent._disk()
        )
        folder_meta = FolderMetadata(
            id=meta.id,
            name=meta.name,
            kind=WORKSPACE_EXPERIMENT_KIND,
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )
        attrs = cls.base_from_disk_attrs(
            parent, folder_meta, slug=parent._disk().basename(child_dir)
        ) | {
            "_entity_metadata": meta,
            "_staged_document": None,
        }
        return _reconstruct(cls, attrs)

    # ── Properties (entity-specific) ─────────────────────────────────────

    @property
    def project(self) -> Project:
        """The owning :class:`Project` (alias for :attr:`Folder.parent`)."""
        if self._parent is None:  # pragma: no cover — Experiment always has a parent
            raise RuntimeError("Experiment has no parent project")
        return cast("Project", self._parent)

    @property
    def metadata(self) -> ExperimentMetadata:  # type: ignore[override]
        return self._entity_metadata

    @metadata.setter
    def metadata(self, value: ExperimentMetadata) -> None:
        self._entity_metadata = value

    @property
    def id(self) -> str:
        return self._entity_metadata.id

    @property
    def name(self) -> str:
        return self._entity_metadata.name

    @property
    def created_at(self):  # noqa: ANN201
        return self._entity_metadata.created_at

    @property
    def description(self) -> str:
        return self._entity_metadata.description

    @property
    def tags(self) -> list[str]:
        return self._entity_metadata.tags

    @property
    def workflow_kind(self) -> WorkflowKind | None:
        """``"code"``, ``"document"``, or ``None`` when this experiment is unbound."""
        return self._entity_metadata.workflow_kind

    @property
    def workflow_document(self) -> dict[str, JSONValue] | None:
        """The IR in ``workflow.ir.json``, or ``None`` when the file is absent.

        A non-object payload is ``None``. The document is opaque. This accessor
        does not read ``experiment.json``.
        """
        doc_path = self._disk().join(self.experiment_dir, WORKFLOW_DOC_FILENAME)
        if not self._disk().is_file(doc_path):
            return None
        with self._disk().open(doc_path) as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else None

    def bind_workflow(
        self,
        kind: str,
        *,
        entrypoint: str | None = None,
        document: dict[str, JSONValue] | None = None,
    ) -> None:
        """Record this experiment's one workflow association and save it.

        A first bind, a code-to-code rebind, and re-binding the same document
        keep the revision. Editing a document, or converting between code and
        document, stamps a new revision. Validation failures leave the disk
        unchanged.

        Args:
            kind: ``"code"`` or ``"document"``.
            entrypoint: Locator for a code workflow. Ignored as a clear when
                *kind* is ``"document"`` and must then be omitted.
            document: Opaque IR for a document workflow.

        Raises:
            ValueError: *kind* is unknown, a document is missing its IR, or a
                document also names an entrypoint.
            TypeError: *document* is not a dict.
        """
        updates, revise = self._binding_updates(kind, entrypoint=entrypoint, document=document)
        self._write_workflow_doc(document)
        self._apply_definition(updates, revise=revise, document=document)

    @property
    def parameter_space(self) -> dict[str, JSONValue]:
        return self._entity_metadata.parameter_space

    @property
    def params(self) -> dict[str, JSONValue]:
        """Concrete parameter dict bound to this experiment."""
        return self._entity_metadata.parameter_space

    @property
    def n_replicas(self) -> int:
        return self._entity_metadata.n_replicas

    @property
    def seeds(self) -> list[int] | None:
        return self._entity_metadata.seeds

    @property
    def entrypoint(self) -> str | None:
        """``"<file>:<qualname>"`` of a code workflow, or ``None`` when unbound.

        Written when a code workflow is bound. A document workflow leaves this
        empty and keeps its IR in :attr:`workflow_document`.
        """
        return self._entity_metadata.workflow_entrypoint

    @property
    def target(self) -> str | None:
        """Compute target new runs use when none is given."""
        return self._entity_metadata.default_target

    @property
    def workspace(self) -> Workspace:
        return self.project.workspace

    @property
    def experiment_dir(self) -> Path:
        return Path(self._disk().join(self.project.project_dir, EXPERIMENT_CONTAINER, self._name))

    @property
    def scope(self) -> AssetScope:
        return AssetScope(kind="experiment", ids=(self.project.id, self.id))

    @property
    def assets(self) -> AssetRepository:
        """Named, versioned assets at this experiment's scope."""
        from .artifact_repository import AssetRepository

        return AssetRepository(self.project.workspace, self.scope, self.experiment_dir)

    @property
    def data_assets(self) -> AssetRepository:
        """Alias of :attr:`assets`.

        Kept because ``{scope}.data_assets.import_asset`` is a frozen CLAUDE.md contract.
        """
        return self.assets

    def get_seeds(self) -> list[int]:
        """Return replica seeds (length == ``n_replicas``)."""
        seeds = self._entity_metadata.seeds
        if seeds is not None:
            return list(seeds[: self.n_replicas])
        out = list(_DEFAULT_SEEDS)
        while len(out) < self.n_replicas:
            out.append(out[-1] + 111)
        return out[: self.n_replicas]

    # ── Persistence ─────────────────────────────────────────────────────

    def materialize(self) -> None:
        """Create filesystem structure and persist metadata (non-recursive)."""
        d = self.experiment_dir
        self._disk().mkdir(d, parents=True, exist_ok=True)
        if self._staged_document is not None:
            self._write_workflow_doc(self._staged_document)
            self._staged_document = None
        self.save()
        from .scientific_repository import ScientificRepository

        ScientificRepository(self.workspace.root, fs=self._disk()).record_experiment(
            self.metadata.model_dump(mode="json"),
            project_id=self.project.id,
            path=self.experiment_dir,
        )

    def write_meta(self) -> str:
        """Stamp concept ``type`` on ``experiment.json``."""
        self.save()
        return self._disk().join(self.experiment_dir, "experiment.json")

    def _move_target_id(self, new_name: str | None) -> str:
        """An Experiment keeps its UUID id across a move; only the name changes."""
        del new_name
        return self._name

    def _sync_entity_identity(self) -> None:
        """Mirror the human name into ``experiment.json`` (``move_to`` hook).

        The UUID id (and directory basename) is stable across a move. The
        definition digest follows the new name; revision is not bumped and
        ``workflow.ir.json`` is not written.
        """
        self._stage_definition({"name": self._metadata.name})
        self.save()

    def _binding_updates(
        self,
        kind: str,
        *,
        entrypoint: str | None,
        document: dict[str, JSONValue] | None,
    ) -> tuple[dict[str, object], bool]:
        """Validate a bind and return ``(metadata updates, revise)``.

        Raises:
            ValueError: The kind and the references disagree.
            TypeError: *document* is not a dict.
        """
        if kind not in ("code", "document"):
            raise ValueError(f"workflow kind must be 'code' or 'document', got {kind!r}")
        if document is not None and not isinstance(document, dict):
            raise TypeError("workflow document must be a dict")
        if kind == "document":
            if document is None:
                raise ValueError("a document workflow requires a document")
            if entrypoint is not None:
                raise ValueError("a document workflow cannot also name an entrypoint")
        prev = self.metadata
        prev_doc = self.workflow_document
        had_binding = (
            prev.workflow_kind is not None or bool(prev.workflow_entrypoint) or prev_doc is not None
        )
        prev_was_reference = prev.workflow_kind == "code" or (
            prev.workflow_kind is None and bool(prev.workflow_entrypoint)
        )
        revise = (
            kind == "document" and had_binding and (prev_was_reference or prev_doc != document)
        ) or (prev.workflow_kind == "document" and kind != "document")
        return {
            "workflow_kind": kind,
            "workflow_entrypoint": None if kind == "document" else entrypoint,
        }, revise

    def _stage_definition(
        self,
        updates: dict[str, object],
        *,
        document: dict[str, JSONValue] | object | None = _CURRENT,
    ) -> None:
        """Merge *updates* and recompute ``definition_hash``. No I/O.

        Args:
            updates: Metadata fields to merge.
            document: IR to fold into the hash. The default reads the current
                ``workflow.ir.json`` when the merged kind is ``"document"``.
                An explicit value is remembered as :attr:`_staged_document` so
                :meth:`materialize` can write it before ``experiment.json``.
        """
        staged = self._entity_metadata.model_copy(update=updates)
        if document is _CURRENT:
            folded = self.workflow_document if staged.workflow_kind == "document" else None
        else:
            folded = cast(
                "dict[str, JSONValue] | None",
                document if isinstance(document, dict) else None,
            )
            self._staged_document = folded
        digest = _experiment_definition_hash(staged.model_dump(), document=folded)
        self._entity_metadata = staged.model_copy(update={"definition_hash": digest})

    def _apply_definition(
        self,
        updates: dict[str, object],
        *,
        revise: bool,
        document: dict[str, JSONValue] | object | None = _CURRENT,
    ) -> None:
        """Stage *updates*, optionally stamp a revision, save, then record history.

        Does not write ``workflow.ir.json``. The caller writes that first.
        Clears :attr:`_staged_document` after the metadata save.
        """
        from datetime import UTC, datetime

        self._stage_definition(updates, document=document)
        if revise:
            self._entity_metadata = self._entity_metadata.model_copy(
                update={
                    "revision_id": generate_uuid7(),
                    "revision": self._entity_metadata.revision + 1,
                    "revision_created_at": datetime.now(UTC),
                }
            )
        self.save()
        self._staged_document = None
        if revise:
            from .scientific_repository import ScientificRepository

            ScientificRepository(self.workspace.root, fs=self._disk()).record_experiment_revision(
                self.metadata.model_dump(mode="json"),
                project_id=self.project.id,
                path=self.experiment_dir,
            )

    def save(self) -> None:
        """Persist current metadata to ``experiment.json``.

        Does not write or delete ``workflow.ir.json``. That file has one writer,
        :meth:`_write_workflow_doc`.
        """
        _save_metadata(
            self._entity_metadata,
            self._disk().join(self.experiment_dir, "experiment.json"),
            fs=self._disk(),
        )

    @property
    def _workflow_doc_path(self) -> str:
        """Path of the standalone :data:`WORKFLOW_DOC_FILENAME` IR file."""
        return self._disk().join(self.experiment_dir, WORKFLOW_DOC_FILENAME)

    def _write_workflow_doc(self, document: dict[str, JSONValue] | None) -> None:
        """Write or delete ``workflow.ir.json``. The only writer of that file.

        Args:
            document: IR object to store, or ``None`` to delete the file when
                it exists. Does not touch ``experiment.json`` or ``workflow.json``.
        """
        doc_path = self._workflow_doc_path
        if document is not None:
            self._disk().atomic_write_json(doc_path, document)
            return
        if self._disk().is_file(doc_path):
            self._disk().remove(doc_path)

    # ── Run CRUD: typed semantic sugar over generic Folder CRUD ────────────

    def add_run(
        self,
        params: dict[str, JSONValue] | None = None,
        *,
        id: str | None = None,
        target: str | None = None,
        inputs: tuple[str, ...] = (),
        config_hash: str | None = None,
    ) -> Run:
        """Add a new logical Run under this Experiment.

        ``params`` may be positional. The run's directory is its parameters
        (``dp=5_seed=42``); ``id=`` overrides only the UUIDv7 identity. Re-adding the
        ``definition_hash`` supports comparison and duplicate detection, but
        never substitutes for identity: every call without an explicit id gets
        a fresh UUIDv7 Run. ``config_hash`` (the profile configuration's hash)
        folds into ``definition_hash`` when given; see
        :func:`~molab.workspace.run.compute_run_definition_hash`. To find an
        existing run by its definition instead, use :meth:`ensure_run`.
        """
        definition_hash = compute_run_definition_hash(
            experiment_revision_id=self.metadata.revision_id,
            parameters=params,
            input_asset_ids=inputs,
            config_hash=config_hash,
        )
        resolved_id = id if id is not None else generate_uuid7()
        resolved_target = target if target is not None else self._entity_metadata.default_target
        _validate_target_registered(self.workspace, resolved_target)
        siblings = self.list_runs()
        if id is not None:
            for sibling in siblings:
                if sibling.id == id:
                    return self.get_folder(sibling._name, cls=Run)
        slug = disambiguate(
            run_slug(params, fallback=definition_hash),
            {run._name for run in siblings},
        )
        child = self._construct_child(
            Run,
            slug,
            id=resolved_id,
            parameters=params,
            target=resolved_target,
            definition_hash=definition_hash,
            experiment_revision_id=self.metadata.revision_id,
            inputs=inputs,
        )
        return self.add_folder(child)

    def add_runs(
        self,
        space: ParamSpace,
        *,
        target: str | None = None,
    ) -> list[Run]:
        """Add one fresh UUID-addressed Run per cell in a ParamSpace."""
        runs: list[Run] = []
        for cell in space:
            cell_params = dict(cell)
            runs.append(
                self.add_run(
                    params=cast("dict[str, JSONValue]", cell_params),
                    target=target,
                )
            )
        return runs

    def ensure_run(
        self,
        params: dict[str, JSONValue] | None = None,
        *,
        config_hash: str | None = None,
        target: str | None = None,
        inputs: tuple[str, ...] = (),
    ) -> Run:
        """Return the Run with this definition, creating it if there is none.

        The one "find by ``definition_hash`` or create" verb. The hash is
        :func:`~molab.workspace.run.compute_run_definition_hash` over this
        experiment's revision, ``params``, ``inputs`` and
        ``config_hash``; among existing runs whose ``definition_hash``
        matches, the earliest created (ties broken by run id) is returned. On a miss the run is
        created through :meth:`add_run`, so it gets a fresh UUIDv7 id — there
        is deliberately no ``id=`` here.

        ``target`` is used only when creating: execution location is not
        identity, so it never takes part in the lookup. A run added by
        :meth:`add_run` without a config is found again by
        ``ensure_run(params)``; the same params under a different
        ``config_hash`` are a different run (its directory disambiguates,
        e.g. ``a=1`` / ``a=1-2``).

        Not safe against concurrent processes: two callers racing on the same
        definition may each create a run, exactly as with :meth:`add_run`.

        Args:
            params: The run's parameter cell.
            config_hash: Profile configuration hash, or ``None`` for none.
            target: Compute target for a newly created run.
            inputs: Declared input asset ids.

        Returns:
            The existing or newly created (and persisted) :class:`Run`.
        """
        run, _ = self._ensure_run(
            params,
            config_hash=config_hash,
            target=target,
            inputs=inputs,
            index=self._definition_index(),
        )
        return run

    def find_run(
        self,
        params: dict[str, JSONValue] | None = None,
        *,
        config_hash: str | None = None,
        inputs: tuple[str, ...] = (),
    ) -> Run | None:
        """Return the Run with this definition, or ``None`` when there is none.

        The read-only half of :meth:`ensure_run`: the same
        :func:`~molab.workspace.run.compute_run_definition_hash` over this
        experiment's revision, ``params``, ``inputs`` and
        ``config_hash``, looked up in the same index (earliest created wins
        among duplicates). It never creates a run.

        Args:
            params: The run's parameter cell.
            config_hash: Profile configuration hash, or ``None`` for none.
            inputs: Declared input asset ids.

        Returns:
            The existing :class:`Run`, or ``None`` if no run has this definition.
        """
        definition_hash = compute_run_definition_hash(
            experiment_revision_id=self.metadata.revision_id,
            parameters=params,
            input_asset_ids=inputs,
            config_hash=config_hash,
        )
        return self._definition_index().get(definition_hash)

    def _definition_index(self) -> dict[str, Run]:
        """Map each ``definition_hash`` to its earliest-created run.

        Duplicates (``add_run`` allocates a fresh run every call) resolve by
        the record — earliest ``created_at``, then run id — never by
        directory name, so renaming a run directory cannot change the answer.
        """
        runs = sorted(self.list_runs(), key=lambda r: (r.metadata.created_at, r.id))
        index: dict[str, Run] = {}
        for run in runs:
            index.setdefault(run.metadata.definition_hash, run)
        return index

    def _ensure_run(
        self,
        params: dict[str, JSONValue] | None,
        *,
        config_hash: str | None,
        target: str | None,
        inputs: tuple[str, ...],
        index: dict[str, Run],
    ) -> tuple[Run, bool]:
        """Find the run for this definition in *index*, or create and index it.

        Returns:
            ``(run, created)`` — ``created`` is ``True`` only for a new run.
        """
        definition_hash = compute_run_definition_hash(
            experiment_revision_id=self.metadata.revision_id,
            parameters=params,
            input_asset_ids=inputs,
            config_hash=config_hash,
        )
        existing = index.get(definition_hash)
        if existing is not None:
            return existing, False
        run = self.add_run(
            params,
            config_hash=config_hash,
            target=target,
            inputs=inputs,
        )
        index.setdefault(definition_hash, run)
        return run, True

    def _seed_missing_runs(
        self,
        space: ParamSpace,
        *,
        target: str | None = None,
    ) -> list[Run]:
        """Seed one fresh Run per *not yet present* cell (idempotent).

        :meth:`add_runs` materializes every cell unconditionally — a Run is
        immutable intent, so re-adding creates fresh Runs. ``define`` and
        ``sweep`` are the *seeding* verbs and stay idempotent: each cell goes
        through :meth:`_ensure_run`, so a cell whose ``definition_hash``
        already exists is skipped, re-declaring the same sweep returns only
        newly-created runs (an empty list on a repeat declaration) and never
        duplicates.
        """
        index = self._definition_index()
        runs: list[Run] = []
        for cell in space:
            run, created = self._ensure_run(
                cast("dict[str, JSONValue]", dict(cell)),
                config_hash=None,
                target=target,
                inputs=(),
                index=index,
            )
            if created:
                runs.append(run)
        return runs

    def define(
        self,
        workflow: object,
        *,
        params: ParamSpace | Mapping[str, JSONValue] | None = None,
    ) -> Experiment:
        """Define that this experiment executes *workflow* over *params*.

        Seeds one content-addressed :class:`Run` per param cell (idempotent)
        and binds *workflow* through the workflow executor seam.

        Returns:
            ``self`` for chaining (``.list_runs()`` …).
        """
        from molab.param import GridSpace, ParamSpace

        space = (
            params if isinstance(params, ParamSpace) else GridSpace(dict(params or {}))  # ty: ignore[invalid-argument-type]
        )
        self._seed_missing_runs(space)
        if _workflow_executor is None:
            raise RuntimeError(
                "Experiment.define needs the workflow layer; `import molab` "
                "(not just `molab.workspace`) registers the executor."
            )
        _workflow_executor(self, workflow)
        return self

    def run(
        self,
        id_or_workflow: str | object,
        /,
        *,
        params: ParamSpace | Mapping[str, JSONValue] | None = None,
    ) -> Run | Experiment:
        """Get a run by id, or define a workflow.

        * **str** → :meth:`get_run` (must exist).
        * **workflow object** → :meth:`define`.
        """
        if isinstance(id_or_workflow, str):
            return self.get_run(id_or_workflow)
        return self.define(id_or_workflow, params=params)

    def sweep(
        self,
        workflow: object,
        params: ParamSpace | Mapping[str, JSONValue] | None = None,
    ) -> RunSet:
        """Seed the *params* sweep for *workflow* and return the RunSet.

        The batch-execution twin of :meth:`run` — identical idempotent
        seeding (one :class:`Run` per cell; a repeat declaration of the same
        sweep adds no new runs and returns an empty
        :class:`~molab.workspace.runset.RunSet`) and identical workflow
        association through the cross-layer :class:`WorkflowExecutor` seam,
        but it returns the newly-seeded :class:`~molab.workspace.runset.RunSet`
        so the caller can drive and summarize the batch directly::

            summary = exp.sweep(wf, {"lr": [1e-3, 1e-4], "batch": [16, 32]}).execute()
            best = summary.min_by("loss")

        ``params`` is a ``{axis: [values]}`` grid mapping (auto-upgraded to
        :class:`~molab.param.GridSpace`; every axis must map to a
        *list* of values — a scalar axis fails fast) or any
        :class:`~molab.param.ParamSpace`. ``None`` seeds a single
        parameter-free run. *workflow* may be an uncompiled
        ``Workflow``; the workflow-layer executor compiles it.
        """
        from molab.param import GridSpace, ParamSpace

        from .runset import RunSet

        if params is None or isinstance(params, ParamSpace):
            space: ParamSpace = params if params is not None else GridSpace({})
        else:
            grid = dict(params)
            scalars = [axis for axis, values in grid.items() if not isinstance(values, list)]
            if scalars:
                raise ValueError(
                    f"sweep params must map every axis to a list of values; "
                    f"got a scalar for {', '.join(repr(a) for a in scalars)} — "
                    f"wrap it in a list (e.g. {scalars[0]!r}: [{grid[scalars[0]]!r}])."
                )
            # Rebuild through the isinstance filter the guard above already
            # proved exhaustive, so the axis type is carried, not asserted.
            space = GridSpace(
                {axis: values for axis, values in grid.items() if isinstance(values, list)}
            )
        runs = self._seed_missing_runs(space)
        if _workflow_executor is None:
            raise RuntimeError(
                "Experiment.sweep needs the workflow layer; `import molab` "
                "(not just `molab.workspace`) registers the executor."
            )
        _workflow_executor(self, workflow)
        return RunSet(runs, workflow=workflow)

    def runset(self) -> RunSet:
        """All existing runs as a :class:`~molab.workspace.runset.RunSet`.

        The batch view over :meth:`list_runs` — read back a finished sweep
        (``exp.runset().collect().to_records()``) or execute still-pending runs
        (the workflow resolves from the experiment's binding at execute time).
        """
        from .runset import RunSet

        return RunSet(self.list_runs())

    def runs(self) -> RunSet:
        """Deprecated alias of :meth:`runset`."""
        import warnings

        warnings.warn(
            "Experiment.runs() is deprecated; use runset()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.runset()

    def get_run(self, run_id: str) -> Run:
        """Get a run by its directory name (its parameters) or its UUIDv7 id."""
        return self.get_folder(run_id, cls=Run)

    def set_run(
        self,
        run_id: str,
        *,
        params: dict[str, JSONValue] | None = None,
        target: str | None = None,
    ) -> Run:
        """Reject mutation of a Run's scientific definition.

        Schema v2 assigns every Run a stable logical identity. Changes to
        parameters, inputs, or target create a new Run.
        """
        run = self.get_run(run_id)
        if params is None and target is None:
            return run
        raise RuntimeError(
            "Run definitions are immutable in schema v2; create a new Run "
            "instead of changing parameters, workflow, inputs, or target"
        )

    def del_run(self, run_id: str) -> None:
        """Delete a run directory."""
        self.remove_folder(run_id, cls=Run)

    def has_run(self, run_id: str) -> bool:
        return self.has_folder(run_id, cls=Run)

    def remove_run(self, run_id: str) -> None:
        """Alias of :meth:`del_run`."""
        self.del_run(run_id)

    # ── Internal helpers ────────────────────────────────────────────────

    def list_runs(self) -> list[Run]:
        """List all runs by scanning the ``runs/`` directory.

        One ``scandir`` pass answers which entries are directories; a
        directory counts as a run only when it holds a ``run.json``.

        Returns:
            The runs, ordered by directory name.
        """
        result: list[Run] = []
        disk = self._disk()
        runs_dir = disk.join(self.experiment_dir, RUN_CONTAINER)
        if not disk.is_dir(runs_dir):
            return result
        entries = disk.scandir(runs_dir, with_stat=False)
        for entry in sorted(entries, key=lambda e: e.name):
            if not entry.is_dir:
                continue
            entry_path = disk.join(runs_dir, entry.name)
            if disk.exists(disk.join(entry_path, "run.json")):
                result.append(Run.from_disk(entry_path, self))
        return result

    def children(self, kind: str | None = None) -> list[Folder]:
        """List entity children (currently only :class:`Run`)."""
        if kind is not None and kind != WORKSPACE_RUN_KIND:
            return []
        return list(self.list_runs())
