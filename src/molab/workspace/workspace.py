"""Workspace: top-level container with project management.

The Workspace is the root of the hierarchy and the only :class:`Folder`
whose ``parent`` is ``None``. It holds the disk backend. Every Folder,
including the Workspace, exposes that disk as :attr:`Folder.fs`.
Child Folders are locations on that disk; they resolve I/O through
:meth:`Folder._disk` and expose user writes as :attr:`Folder.files`.

Construction is in memory. A root with no ``index.md`` record gets a new
UUIDv7 id, written later, create-if-absent, by ``materialize`` or the first
``add_project``. A record already on disk is kept.

Child factories (``.add_project(...)``) are idempotent: they load existing
children from disk or create + materialize new ones.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path as _LocalPath
from typing import TYPE_CHECKING, cast

from molab._typing import JSONValue
from molab.ids import generate_uuid7
from molab.path import Path

from .base import _load_metadata, _record_payload
from .domain import AssetScope
from .entity_record import INDEX_FILENAME, read_record, read_type
from .errors import ProjectExistsError, ProjectNotFoundError
from .folder import (
    WORKSPACE_PROJECT_KIND,
    WORKSPACE_ROOT_KIND,
    Folder,
    register_entity_class,
)
from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .models import FolderMetadata, WorkspaceMetadata
from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER
from .project import Project
from .validate import ValidationReport, validate_workspace

if TYPE_CHECKING:
    from .artifact_repository import AssetRepository
    from .domain import Artifact, Asset, Execution
    from .experiment import Experiment
    from .models import ComputeTarget
    from .refs import MolabRef
    from .run import Run
    from .workspace_context import ContextFocus, WorkspaceContext
    from .wp import WorkspacePaths

# CLI-level root override: set by ``molab run`` before executing the user
# script so a script's ``me.Workspace(...)`` resolves against the CLI instead
# of (or, when rootless, in place of) its hardcoded argument. Stored as
# ``(path, explicit)`` or ``None``:
#   * ``explicit=True``  — an explicit ``-ws/--workspace`` flag: STRONG, wins
#     even over a root the script passed (the original CLI-flag behavior).
#   * ``explicit=False`` — an inferred root (the entry-script directory, set
#     when no flag is given): WEAK, only fills in when the script omits its
#     root, so a script that passes an explicit root keeps it.
# ``None`` means no override — ``Workspace(root)`` uses the caller's root as-is.
_cli_root_override: tuple[_LocalPath, bool] | None = None


def set_cli_root_override(path: _LocalPath | str | None, *, explicit: bool = True) -> None:
    """Set (or clear) the CLI-level workspace root override.

    Args:
        path: The override root, or ``None`` to clear it.
        explicit: ``True`` (default) for an explicit ``-ws`` flag — wins over a
            root the script hardcodes. ``False`` for an inferred root (entry
            script directory) — used only when the script omits its root.

    Intended solely for ``molab run`` to make the CLI flag authoritative, or
    to fill in a rootless ``Workspace(name=...)`` with the script's directory.
    """
    global _cli_root_override
    _cli_root_override = (_LocalPath(path).resolve(), explicit) if path is not None else None


def _lexical_parent(parent: str, current: str) -> bool:
    """Whether *parent* is the strict lexical parent of *current*.

    ``"."`` is the parent of a relative single segment. ``"/"`` is the parent
    of every other absolute path. Anything else must be a real path prefix.
    """
    if parent == current:
        return False
    if parent == "/":
        return current.startswith("/") and current != "/"
    if parent == ".":
        return "/" not in current
    return current.startswith(parent.rstrip("/") + "/")


@register_entity_class
class Workspace(Folder):
    """Top-level workspace with project management and global asset library.

    Inherits :class:`Folder` (sub-spec 02): ``kind`` is
    :data:`WORKSPACE_ROOT_KIND`, ``parent`` is ``None``. The workspace
    is its own root — :meth:`resolve` returns :attr:`root`
    directly rather than nesting one level deeper like other Folder
    subclasses.

    Example::

        ws = Workspace("./lab")
        project = ws.add_project("QM9")
        exp = project.add_experiment("baseline", params={"lr": 1e-3}, n_replicas=3)
    """

    _exists_error_cls = ProjectExistsError
    _not_found_error_cls = ProjectNotFoundError
    _entity_kind = WORKSPACE_ROOT_KIND

    def __init__(
        self, root: PathArg | None = None, name: str | None = None, *, fs: FileSystem | None = None
    ) -> None:
        self._disk_backend = fs or LocalFileSystem()

        # Root precedence (local only). An explicit ``-ws`` override is STRONG
        # and wins over a script-passed root; an inferred override is WEAK and
        # only fills in when ``root`` is omitted. With no override, the passed
        # root is used as-is; with neither root nor override we fail fast.
        local = isinstance(self.fs, LocalFileSystem)
        override = _cli_root_override if local else None
        if override is not None and (root is None or override[1]):
            resolved_raw = str(override[0])
        elif root is None:
            raise ValueError(
                "Workspace root not given and no CLI override set — "
                "pass a root or run the script via `molab run`"
            )
        elif local:
            resolved_raw = self.fs.resolve(str(root))
        else:
            resolved_raw = str(root)  # Remote: use path as-is (tilde handled by remote shell)

        record = read_record(self.fs, resolved_raw)
        if record is not None and record.type == WORKSPACE_ROOT_KIND:
            entity_meta = _load_metadata(WorkspaceMetadata, record.canonical)
        else:
            display_name = name if name is not None else self.fs.basename(resolved_raw)
            entity_meta = WorkspaceMetadata(id=generate_uuid7(), name=display_name)

        # Workspace bypasses ``Folder.__init__`` because the human-readable
        # ``name`` may contain characters (e.g. spaces, uppercase) that the
        # ``_KIND_PATTERN`` validator rejects. The id is an owner-minted
        # UUIDv7 (a legacy workspace keeps the slug already on disk); ``name``
        # may contain any character.
        self._parent = None
        self._name = entity_meta.id
        self._kind = WORKSPACE_ROOT_KIND
        self._root_path: Path = Path(resolved_raw)
        self._metadata = FolderMetadata(
            id=entity_meta.id,
            name=entity_meta.name,
            kind=WORKSPACE_ROOT_KIND,
            created_at=entity_meta.created_at,
            updated_at=entity_meta.created_at,
        )
        self._children_cache = {}
        self._serve_boundary = False

        # Entity-specific state — ``root`` is :class:`molab.Path` for both
        # local and remote workspaces; wrap with :class:`pathlib.Path` at
        # genuine-local-I/O sites.
        self.root: Path = self._root_path
        self._entity_metadata: WorkspaceMetadata = entity_meta

    # ── Folder hooks ─────────────────────────────────────────────────────

    def resolve(self) -> Path:
        """Workspace IS its own on-disk dir; no parent nesting."""
        return self._root_path

    @classmethod
    def from_disk(cls, child_dir: PathArg, parent: Folder) -> Workspace:
        """Reconstruct a Workspace rooted at *child_dir* (OKF concept rebuild).

        A Workspace is its own root, so the generic :meth:`Folder.from_disk`
        cannot rebuild it. ``concept_from_dir`` reaches here when the root
        ``index.md`` carries ``type: workspace.root``; the constructor reloads
        that record from *child_dir* and ignores the synthetic *parent* (a
        Workspace has none). See the Folder.from_disk hook docs.
        """
        return cls(root=child_dir, fs=parent._disk())

    @staticmethod
    def enclosing_root(path: PathArg, *, fs: FileSystem | None = None) -> Path | None:
        """Return the nearest ancestor-or-self of *path* whose ``index.md`` is a workspace root.

        The walk is lexical. This method does not resolve symlinks, ignores the
        CLI root override, and never constructs a Workspace. A relative path is
        walked relative to the current directory, and that directory is the
        last candidate. An empty dirname of an absolute path is the filesystem
        root, probed once; a parent that is not a strict lexical ancestor stops
        the walk without being probed. There is exactly one ``is_file`` probe
        per candidate, up to and including the hit. A candidate that has an
        ``index.md`` gets its head read (``read_range`` only, up to the closing
        fence) to see whether its ``type`` is ``workspace.root``; there is no
        ``open`` / ``read_text`` / ``scandir`` / ``stat`` / ``exists``.

        Args:
            path: A file or directory, in the caller's spelling.
            fs: Filesystem to probe. Defaults to a local filesystem.

        Returns:
            The enclosing root, keeping the caller's spelling, or ``None``.
        """
        disk = fs if fs is not None else LocalFileSystem()
        current = str(path)
        while True:
            if (
                disk.is_file(disk.join(current, INDEX_FILENAME))
                and read_type(disk, current) == WORKSPACE_ROOT_KIND
            ):
                return Path(current)
            parent = disk.dirname(current)
            if parent == "" and current.startswith("/"):
                parent = "/"
            if parent == current or not _lexical_parent(parent, current):
                return None
            current = parent

    @staticmethod
    def machine_dir(root: PathArg) -> Path:
        """Machine directory under *root*.

        Locks, caches and other state a person does not open. The caller
        creates any child path. This does not construct a Workspace, ignores
        the CLI root override, and does no I/O.

        Args:
            root: Directory the caller already holds. Its spelling is kept.

        Returns:
            ``<root>/.molab`` as a :class:`molab.path.Path`.
        """
        from .history import MOLAB_DIR

        return Path(str(root)) / MOLAB_DIR

    @staticmethod
    def list_hosts(root: PathArg, *, fs: FileSystem | None = None) -> Iterator[Path]:
        """Yield *root*, then each project, experiment and run directory under it.

        Callers pass a root from :meth:`enclosing_root` or a Workspace's
        ``root``. This method does not check that *root* is a workspace. It
        calls ``scandir(with_stat=False)`` only and reads no record. A
        missing container is skipped. Names starting with ``.`` are skipped.
        Siblings are sorted by name. A run directory is yielded; nothing
        inside it is listed. Every yielded path is joined from *root*, so the
        caller's spelling is kept. The CLI root override is ignored. No record
        is read.

        Args:
            root: Directory to enumerate.
            fs: Filesystem to list. Defaults to a local filesystem.

        Yields:
            ``root``, then project, experiment and run directories in pre-order.
        """
        disk = fs if fs is not None else LocalFileSystem()
        root_s = str(root)
        yield Path(root_s)

        def _child_dirs(container: str) -> list[str]:
            try:
                entries = disk.scandir(container, with_stat=False)
            except OSError:
                return []
            return sorted(
                entry.name for entry in entries if entry.is_dir and not entry.name.startswith(".")
            )

        for project_name in _child_dirs(disk.join(root_s, PROJECT_CONTAINER)):
            project_path = disk.join(root_s, PROJECT_CONTAINER, project_name)
            yield Path(project_path)
            for experiment_name in _child_dirs(disk.join(project_path, EXPERIMENT_CONTAINER)):
                experiment_path = disk.join(project_path, EXPERIMENT_CONTAINER, experiment_name)
                yield Path(experiment_path)
                for run_name in _child_dirs(disk.join(experiment_path, RUN_CONTAINER)):
                    yield Path(disk.join(experiment_path, RUN_CONTAINER, run_name))

    def _read_entity_metadata(self) -> WorkspaceMetadata | None:
        """The workspace record on disk, or ``None`` when the root has none yet."""
        record = read_record(self.fs, self.resolve())
        if record is None or record.type != WORKSPACE_ROOT_KIND:
            return None
        return _load_metadata(WorkspaceMetadata, record.canonical)

    def _ensure_materialized(self) -> None:
        existing = self._read_entity_metadata()
        if existing is None:
            self.materialize()
            return
        self._adopt_entity_metadata(existing)

    def _adopt_entity_metadata(self, meta: WorkspaceMetadata) -> None:
        """Take *meta* as this handle's identity (disk won a create race)."""
        self._entity_metadata = meta
        self._name = meta.id
        self._metadata = FolderMetadata(
            id=meta.id,
            name=meta.name,
            kind=WORKSPACE_ROOT_KIND,
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )

    def _create_lock_path(self) -> _LocalPath:
        from .history import MOLAB_DIR

        lock_dir = self.fs.join(self.resolve(), MOLAB_DIR, "locks")
        self.fs.mkdir(lock_dir, parents=True, exist_ok=True)
        return _LocalPath(self.fs.join(lock_dir, "workspace.create.lock"))

    def _persist_if_absent(self) -> None:
        """Write the root ``index.md`` record once. A lost race reloads the winner's id."""
        from molab.atomicio import file_lock

        backend = "flock" if isinstance(self.fs, LocalFileSystem) else "none"
        with file_lock(self._create_lock_path(), backend=backend):
            existing = self._read_entity_metadata()
            if existing is not None:
                self._adopt_entity_metadata(existing)
                return
            self._write_record(self._canonical_record())
        self._record_written()

    # ── Properties (entity-specific) ─────────────────────────────────────

    @property
    def metadata(self) -> WorkspaceMetadata:  # type: ignore[override]
        """Workspace-entity metadata (shadows :attr:`Folder.metadata`).

        :attr:`Folder.folder_metadata` still returns the kind-uniform
        :class:`FolderMetadata` view.
        """
        return self._entity_metadata

    @metadata.setter
    def metadata(self, value: WorkspaceMetadata) -> None:
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
    def targets(self) -> list[ComputeTarget]:
        return list(self._entity_metadata.targets)

    @property
    def scope(self) -> AssetScope:
        return AssetScope(kind="workspace", ids=())

    @property
    def assets(self) -> AssetRepository:
        """Named, versioned assets at workspace scope."""
        from .artifact_repository import AssetRepository

        return AssetRepository(self, self.scope, self.root)

    def assets_at(self, scope: AssetScope) -> AssetRepository:
        """The repository for *scope*, resolved by id.

        ``workspace`` is this workspace. ``project`` and ``experiment`` reuse
        the host ``find`` returns. Named assets have no run scope.

        Args:
            scope: Scope whose repository to return.

        Returns:
            The repository bound to that host.

        Raises:
            ValueError: *scope* is a run.
            RefNotFoundError: The project or experiment does not exist.
            AmbiguousRefError: The experiment id matches more than one project.
        """
        from .experiment import Experiment
        from .refs import MolabRef

        if scope.kind == "workspace":
            return self.assets
        if scope.kind == "project":
            return cast(Project, self.find(MolabRef(project_id=scope.ids[0]))).assets
        if scope.kind == "experiment":
            return cast(Experiment, self.find(MolabRef(experiment_id=scope.ids[1]))).assets
        raise ValueError("named assets have no run scope")

    @property
    def data_assets(self) -> AssetRepository:
        """Alias of :attr:`assets`.

        Kept because ``{scope}.data_assets.import_asset`` is a frozen CLAUDE.md contract.
        """
        return self.assets

    # ── Conformance ─────────────────────────────────────────────────────

    def validate(self) -> ValidationReport:
        """Check this workspace against the layout + OKF laws. Writes nothing.

        Reads through this workspace's own filesystem, so a remote workspace
        validates over its own transport. See
        :func:`~molab.workspace.validate.validate_workspace`.
        """
        return validate_workspace(self.resolve(), fs=self.fs)

    def context(self, *, focus: ContextFocus | None = None) -> WorkspaceContext:
        """Assemble the canonical workspace read-model. Writes nothing."""
        from .workspace_context import assemble_workspace_context

        return assemble_workspace_context(self, focus=focus)

    def list_targets(self) -> list[ComputeTarget]:
        from .targets import list_targets as _list

        return _list(self)

    def get_target(self, name: str) -> ComputeTarget:
        from .targets import get_target as _get

        return _get(self, name)

    def has_target(self, name: str) -> bool:
        from .targets import has_target as _has

        return _has(self, name)

    def add_target(self, target: ComputeTarget) -> None:
        from .targets import add_target as _add

        _add(self, target)

    def remove_target(self, name: str) -> None:
        from .targets import remove_target as _remove

        _remove(self, name)

    # ── Path toolkit (layout fixes) ─────────────────────────────────────

    @property
    def wp(self) -> WorkspacePaths:
        """Path ops for layout fixes: ``ws.wp.mv`` / ``ls`` / ``rm`` / ``mkdir``.

        Scoped to this workspace's root and FileSystem (local or remote).
        Free-function form: ``molab.wp.mv(ws, src, dst)``.
        """
        from .wp import WorkspacePaths

        return WorkspacePaths(self)

    # ── Persistence ─────────────────────────────────────────────────────

    def _canonical_record(self) -> dict[str, JSONValue]:
        return _record_payload(self._entity_metadata)

    def _lock_root(self) -> Path:
        return self.resolve()

    def materialize(self) -> None:
        """Write workspace scaffold to disk."""
        root_str = self.resolve()
        self.fs.mkdir(root_str, parents=True, exist_ok=True)
        self._persist_if_absent()

    def save(self) -> None:
        """Persist current metadata to the root ``index.md`` record.

        An id already on disk is kept. A missing record is created once, the
        same way :meth:`materialize` does. The index block and the narrative
        body are kept.
        """
        from molab.atomicio import file_lock

        backend = "flock" if isinstance(self.fs, LocalFileSystem) else "none"
        with file_lock(self._create_lock_path(), backend=backend):
            existing = self._read_entity_metadata()
            if existing is not None:
                self._entity_metadata = self._entity_metadata.model_copy(
                    update={"id": existing.id, "created_at": existing.created_at}
                )
                self._adopt_entity_metadata(self._entity_metadata)
            self._write_record(self._canonical_record())
        self._record_written()

    def find(
        self, ref: MolabRef | str
    ) -> Project | Experiment | Run | Execution | Artifact | Asset:
        """Resolve a ``molab:`` reference by walking entity ids.

        Args:
            ref: A :class:`MolabRef` or its canonical string.

        Returns:
            The project, experiment, run, execution, artifact, or asset it names.

        Raises:
            InvalidRefError: *ref* is a string that is not a canonical reference.
            RefNotFoundError: A segment names nothing in this workspace.
            AmbiguousRefError: An experiment id exists under more than one
                project, or an asset id exists in more than one scope.
        """
        from .artifact_repository import scan_asset_repositories
        from .errors import AmbiguousRefError, RefNotFoundError
        from .experiment import Experiment
        from .refs import MolabRef, parse_ref
        from .run import Run

        parsed = parse_ref(ref) if isinstance(ref, str) else ref
        if parsed.asset_id is not None:
            hits = []
            for repository in scan_asset_repositories(self):
                try:
                    hits.append(repository.get(parsed.asset_id))
                except KeyError:
                    continue
            if not hits:
                raise RefNotFoundError(parsed, segment="asset", entity_id=parsed.asset_id)
            if len(hits) > 1:
                raise AmbiguousRefError(
                    parsed.asset_id,
                    candidates=(),
                    locations=tuple(hit.scope.urn for hit in hits),
                )
            return hits[0]
        if parsed.project_id is not None:
            project = self._child_by_id(parsed.project_id, cls=Project)
            if project is None:
                raise RefNotFoundError(parsed, "project", parsed.project_id)
            return project

        assert parsed.experiment_id is not None
        experiments = [
            experiment
            for project in self.list_projects()
            if (experiment := project._child_by_id(parsed.experiment_id, cls=Experiment))
            is not None
        ]
        if not experiments:
            raise RefNotFoundError(parsed, "experiment", parsed.experiment_id)
        if len(experiments) > 1:
            raise AmbiguousRefError(
                parsed.experiment_id,
                tuple(MolabRef(experiment_id=parsed.experiment_id) for _hit in experiments),
            )
        experiment = experiments[0]
        if parsed.run_id is None:
            return experiment

        run = experiment._child_by_id(parsed.run_id, cls=Run)
        if run is None:
            raise RefNotFoundError(parsed, "run", parsed.run_id)
        if parsed.execution_id is None and parsed.artifact_id is None:
            return run
        if parsed.execution_id is not None:
            for record in run.executions:
                if record.id == parsed.execution_id:
                    return record
            raise RefNotFoundError(parsed, "execution", parsed.execution_id)
        assert parsed.artifact_id is not None
        for record in run.executions:
            try:
                return record.artifact(parsed.artifact_id)
            except KeyError:
                continue
        raise RefNotFoundError(parsed, "artifact", parsed.artifact_id)

    def folder_at(self, path: PathArg) -> Folder | None:
        """The workspace, project, experiment or run whose directory is *path*.

        Workspace owns its layout, so this is where a directory is turned back
        into the Folder that lives there (a caller never assembles one). The
        walk goes down from this workspace's root one level at a time: each
        step must name the next level's container (``projects`` /
        ``experiments`` / ``runs``) and a child whose ``index.md`` record is of
        that level's ``type``. A local path is resolved first, so a symlinked
        spelling of the root still matches.

        Args:
            path: A directory, absolute or as this workspace spells it.

        Returns:
            The Folder, or ``None`` when *path* is outside this workspace or is
            not a level directory (a container, an attempt, a plain directory,
            a directory with no record).
        """
        import posixpath

        from .folder import WORKSPACE_EXPERIMENT_KIND, WORKSPACE_RUN_KIND, concept_from_dir

        disk = self.fs
        local = isinstance(disk, LocalFileSystem)
        root = posixpath.normpath(str(self.resolve()))
        target = posixpath.normpath(disk.resolve(str(path)) if local else str(path))
        if target == root:
            return self
        prefix = root.rstrip("/") + "/"
        if not target.startswith(prefix):
            return None
        parts = target[len(prefix) :].split("/")
        steps = (
            (PROJECT_CONTAINER, WORKSPACE_PROJECT_KIND),
            (EXPERIMENT_CONTAINER, WORKSPACE_EXPERIMENT_KIND),
            (RUN_CONTAINER, WORKSPACE_RUN_KIND),
        )
        if len(parts) % 2 or len(parts) > 2 * len(steps):
            return None
        current: Folder = self
        for (container, kind), index in zip(steps, range(0, len(parts), 2), strict=False):
            if parts[index] != container:
                return None
            child_dir = disk.join(current.resolve(), container, parts[index + 1])
            if read_type(disk, child_dir) != kind:
                return None
            current = concept_from_dir(child_dir, current)
        return current

    def write_meta(self) -> str:
        """Write the workspace record into the root ``index.md``; return its path."""
        self.save()
        return self.fs.join(self.resolve(), INDEX_FILENAME)

    # ── Alternative constructors ─────────────────────────────────────────

    @classmethod
    def load(cls, root: PathArg, *, fs: FileSystem | None = None) -> Workspace:
        """Load an existing workspace from disk (raises if missing).

        Raises:
            FileNotFoundError: *root* has no workspace ``index.md`` record.
            UnmigratedLayoutError: *root* still holds a legacy JSON record.
        """
        _fs = fs or LocalFileSystem()
        root_str = (
            str(_LocalPath(root).resolve()) if isinstance(_fs, LocalFileSystem) else str(root)
        )
        record = read_record(_fs, root_str)
        if record is None or record.type != WORKSPACE_ROOT_KIND:
            raise FileNotFoundError(
                f"Workspace record not found at {_fs.join(root_str, INDEX_FILENAME)}"
            )
        return cls(root, fs=fs)

    # ── Project CRUD (add / get / set / del / list) ────────────────────────

    def add_project(self, name: str) -> Project:
        """Add a project under this workspace (idempotent on slug: same node).

        Writes disk scaffold. Re-adding the same slug returns the existing
        project (does not error). To update fields, use :meth:`set_project`.
        """
        self._ensure_materialized()
        for existing in self.projects():
            if existing.name == name:
                return existing
        child = self._construct_child(Project, name)
        return self.add_folder(child)

    def project(self, name: str) -> Project:
        """Get an existing project by name (must exist).

        Raises:
            ProjectNotFoundError: No project with that slug.
        """
        try:
            return self.get_folder(name, cls=Project)
        except ProjectNotFoundError:
            for project in self.projects():
                if project.name == name:
                    return project
            raise

    def get_project(self, name: str) -> Project:
        """Alias of :meth:`project` (strict getter)."""
        return self.project(name)

    def set_project(
        self,
        name: str,
        *,
        description: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
    ) -> Project:
        """Update fields of an existing project and write to disk.

        Raises:
            ProjectNotFoundError: Project missing.
        """
        proj = self.project(name)
        updates: dict = {}
        if description is not None:
            updates["description"] = description
        if owner is not None:
            updates["owner"] = owner
        if tags is not None:
            updates["tags"] = list(tags)
        if config is not None:
            updates["config"] = dict(config)
        if updates:
            proj._entity_metadata = proj.metadata.model_copy(update=updates)
            proj.save()
        return proj

    def del_project(self, name: str) -> None:
        """Delete a project directory and its children."""
        self.remove_folder(self.project(name).id, cls=Project)

    def has_project(self, name: str) -> bool:
        try:
            self.project(name)
        except ProjectNotFoundError:
            return False
        return True

    def remove_project(self, name: str) -> None:
        """Alias of :meth:`del_project`."""
        self.del_project(name)

    def projects(self) -> list[Project]:
        """List all projects under this workspace."""
        return self.list_folders(cls=Project)

    def list_projects(self) -> list[Project]:
        """Alias of :meth:`projects`."""
        return self.projects()

    def children(self, kind: str | None = None) -> list[Folder]:
        """List entity children (currently only :class:`Project`)."""
        if kind is not None and kind != WORKSPACE_PROJECT_KIND:
            return []
        return list(self.list_projects())
