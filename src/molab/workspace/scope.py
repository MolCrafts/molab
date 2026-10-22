"""Serve-root resolution.

``molab serve`` opens one directory and that directory is the application
root. The kind comes from the entity file already in the directory
(``run.json``, ``experiment.json``, ``project.json``, ``workspace.json``).
A directory with none of those opens as a workspace and nothing is written.

Parents that exist on disk stay attached so path math and history keep
working. The opened folder is marked as the serve boundary: listings and
ancestor ids do not cross it, and no parent is invented when the directory
stands alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from molab.path import Path
from molab.workspace.fs import FileSystem
from molab.workspace.fs_local import LocalFileSystem

if TYPE_CHECKING:
    from molab.workspace.folder import Folder

_OMITTED = {"", "-"}
_DETECT_FILES = ("run.json", "experiment.json", "project.json", "workspace.json")


def as_folder(root: object) -> Folder:
    """Unwrap a :class:`ScopeRoot` or return *root* when it is already a folder."""
    from molab.workspace.folder import Folder

    folder = getattr(root, "folder", None)
    if isinstance(folder, Folder) and folder is not root:
        return folder
    if isinstance(root, Folder):
        return root
    raise TypeError(f"not a folder: {type(root).__name__}")


def rank(node: object) -> int:
    """Hierarchy rank. Unknown kinds sit below the workspace root."""
    from molab.workspace.folder import (
        WORKSPACE_EXPERIMENT_KIND,
        WORKSPACE_PROJECT_KIND,
        WORKSPACE_ROOT_KIND,
        WORKSPACE_RUN_KIND,
    )

    kind = node if isinstance(node, str) else getattr(node, "kind", "")
    return {
        WORKSPACE_ROOT_KIND: 0,
        WORKSPACE_PROJECT_KIND: 1,
        WORKSPACE_EXPERIMENT_KIND: 2,
        WORKSPACE_RUN_KIND: 3,
    }.get(str(kind), -1)


def _class_for_filename(name: str) -> type[Folder]:
    from molab.workspace.experiment import Experiment
    from molab.workspace.folder import class_for_entity_file
    from molab.workspace.project import Project
    from molab.workspace.run import Run
    from molab.workspace.workspace import Workspace

    # Importing the entity modules registers their filenames.
    del Experiment, Project, Run, Workspace
    mapped = class_for_entity_file(name)
    if mapped is None:
        raise KeyError(name)
    return mapped


def _same_id(folder: Folder, ident: str) -> bool:
    if ident in _OMITTED:
        return True
    values = {folder._name, folder.metadata.id}
    entity_id = getattr(folder, "id", None)
    entity_name = getattr(folder, "name", None)
    if entity_id:
        values.add(str(entity_id))
    if entity_name:
        values.add(str(entity_name))
    return ident in values


def display_name(folder: Folder | None) -> str:
    if folder is None:
        return ""
    name = getattr(folder, "name", None)
    return str(name) if name else folder.metadata.name


def entities(root: Folder, cls: type[Folder]) -> list[Folder]:
    """*cls* folders visible from *root*: itself, its children, or nothing above it."""
    if isinstance(root, cls):
        return [root]
    if _rank_of_class(cls) < rank(root):
        return []
    return [child for child in root.list_folders(cls=cls) if isinstance(child, cls)]


def _rank_of_class(cls: type[Folder]) -> int:
    from molab.workspace.experiment import Experiment
    from molab.workspace.folder import (
        WORKSPACE_EXPERIMENT_KIND,
        WORKSPACE_PROJECT_KIND,
        WORKSPACE_ROOT_KIND,
        WORKSPACE_RUN_KIND,
    )
    from molab.workspace.project import Project
    from molab.workspace.run import Run
    from molab.workspace.workspace import Workspace

    kind = {
        Workspace: WORKSPACE_ROOT_KIND,
        Project: WORKSPACE_PROJECT_KIND,
        Experiment: WORKSPACE_EXPERIMENT_KIND,
        Run: WORKSPACE_RUN_KIND,
    }.get(cls, "")
    return rank(kind)


def descendants(root: Folder, cls: type[Folder]) -> list[Folder]:
    """*cls* nodes at or below *root*, one container level at a time."""
    from molab.workspace.experiment import Experiment
    from molab.workspace.project import Project
    from molab.workspace.run import Run

    if isinstance(root, cls):
        return [root]
    if _rank_of_class(cls) < rank(root):
        return []
    chain = (Project, Experiment, Run)
    level: list[Folder] = [root]
    here = rank(root)
    for step in chain:
        if _rank_of_class(step) <= here:
            continue
        nxt: list[Folder] = []
        for node in level:
            nxt.extend(child for child in node.list_folders(cls=step) if isinstance(child, step))
        level = nxt
        if step is cls:
            return level
    return []


def require_entity(root: Folder, cls: type[Folder], ident: str) -> Folder:
    """The *cls* named *ident* inside *root*, or that class's not-found error."""
    if isinstance(root, cls):
        if _same_id(root, ident):
            return root
        raise cls._not_found_error_cls(ident)
    if _rank_of_class(cls) < rank(root):
        raise cls._not_found_error_cls(ident)
    return root.get_folder(ident, cls=cls)


def resolve_in_scope(
    root: object,
    project_id: str | None = None,
    experiment_id: str | None = None,
    run_id: str | None = None,
) -> Folder:
    """Walk project → experiment → run, ignoring ids above the serve root.

    An omitted id (``""`` or ``"-"``) is skipped. An id at the root's own
    rank must name that root. Deeper ids use :meth:`Folder.get_folder`.
    """
    from molab.workspace.experiment import Experiment
    from molab.workspace.project import Project
    from molab.workspace.run import Run

    node = as_folder(root)
    slots = (
        (Project, project_id),
        (Experiment, experiment_id),
        (Run, run_id),
    )
    for cls, ident in slots:
        if ident is None or ident in _OMITTED:
            continue
        level = _rank_of_class(cls)
        here = rank(node)
        if level < here:
            continue
        if level == here:
            if not _same_id(node, ident):
                raise cls._not_found_error_cls(ident)
            continue
        node = node.get_folder(ident, cls=cls)
    return node


def _locate(workspace: Folder, directory: str) -> Folder | None:
    """The entity under *workspace* whose directory is *directory*."""
    target = directory.rstrip("/")
    if str(workspace.resolve()).rstrip("/") == target:
        return workspace
    from molab.workspace.experiment import Experiment
    from molab.workspace.project import Project
    from molab.workspace.run import Run

    for project in descendants(workspace, Project):
        if str(project.resolve()).rstrip("/") == target:
            return project
        for experiment in project.list_folders(cls=Experiment):
            if str(experiment.resolve()).rstrip("/") == target:
                return experiment
            for run in experiment.list_folders(cls=Run):
                if str(run.resolve()).rstrip("/") == target:
                    return run
    return None


class _ServeAnchor:
    """Disk holder for a parentless ``from_disk``. Not a workspace or project."""

    def __init__(self, fs: FileSystem) -> None:
        self._disk_backend = fs

    def _disk(self) -> FileSystem:
        return self._disk_backend


def open_serve_root(path: object, *, fs: FileSystem | None = None) -> Folder:
    """Open *path* as the serve root. Detects the kind. Writes nothing."""
    from molab.workspace.folder import Folder
    from molab.workspace.workspace import Workspace

    disk = fs if fs is not None else LocalFileSystem()
    if isinstance(disk, LocalFileSystem):
        directory = disk.resolve(str(path))
    else:
        directory = str(path)

    found_name: str | None = None
    for name in _DETECT_FILES:
        if disk.exists(disk.join(directory, name)):
            found_name = name
            break
    if found_name is None or found_name == "workspace.json":
        return Workspace(directory, fs=disk)

    cls = _class_for_filename(found_name)
    try:
        enclosing = Workspace.enclosing_root(directory, fs=disk)
    except PermissionError:
        # An authorized project/experiment/run can be mounted without access
        # to its ancestors. Reuse the parentless loader below at that boundary.
        enclosing = None
    if enclosing is not None and str(enclosing).rstrip("/") != directory.rstrip("/"):
        workspace = Workspace(enclosing, fs=disk)
        located = _locate(workspace, directory)
        if located is not None and isinstance(located, cls):
            located._serve_boundary = True
            return located

    # The anchor only supplies ``_disk()``. Entity loaders do not use it as a folder.
    loaded = cls.from_disk(directory, cast("Folder", _ServeAnchor(disk)))
    if not isinstance(loaded, Folder):
        raise TypeError(f"{directory} did not load as a folder")
    loaded._parent = None
    loaded._root_path = Path(directory)
    loaded._disk_backend = disk
    loaded._serve_boundary = True
    return loaded
