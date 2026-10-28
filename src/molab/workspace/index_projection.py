"""The derived ``index:`` zone of a Folder's ``index.md`` (D89).

:func:`project_index` computes, for one level, the reserved keys an agent
reads to walk the tree without listing directories:

==========  ==============================================================
level       keys
==========  ==============================================================
workspace   ``children`` — projects ``{name, path, id, description}``
project     ``parent``, ``children`` — experiments ``{name, path, id,
            description, workflow_kind, entrypoint}``
experiment  ``parent``, ``entrypoint``, ``scratch``, ``children`` — runs
            ``{name, path, id, params}``
run         ``parent``, ``executions`` — per attempt ``{id, path, mode,
            status, started_at, finished_at, job_ids, out, artifacts,
            error}``, ``latest_status``
==========  ==============================================================

A parent row holds only facts that change when the child is added, removed,
renamed, or has a canonical field changed: no hot state and no counts.
Every ``path`` is relative to the file that holds it, rows are sorted by
directory name, and the projection walks only the next level down.

molab never reads this zone to decide anything; the records and the tree
are the truth and this is rebuilt from them. :func:`refresh_index` is how
the owner rewrites it, and a refresh that fails is logged, never raised —
the same policy as history: navigation sugar never fails the science.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from mollog import get_logger

from molab import frontmatter
from molab._typing import JSONValue

from .entity_record import (
    ENTITY_FILENAME,
    RESERVED_INDEX_KEYS,
    EntityRecord,
    update_record,
)
from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER

if TYPE_CHECKING:
    from .folder import Folder
    from .fs import FileSystem, PathArg

_logger = get_logger(__name__)

#: Every level sits two directories below its parent (``<container>/<name>``).
PARENT_INDEX: str = f"../../{ENTITY_FILENAME}"

#: Reserved keys in the order they are written.
_ORDER = ("parent", "entrypoint", "scratch", "children", "executions", "latest_status")

_WORKFLOW_DOC = "workflow.ir.json"
_OUT_DIR = "out"


def _kinds() -> tuple[str, str, str, str]:
    from .folder import (
        WORKSPACE_EXPERIMENT_KIND,
        WORKSPACE_PROJECT_KIND,
        WORKSPACE_ROOT_KIND,
        WORKSPACE_RUN_KIND,
    )

    return (
        WORKSPACE_ROOT_KIND,
        WORKSPACE_PROJECT_KIND,
        WORKSPACE_EXPERIMENT_KIND,
        WORKSPACE_RUN_KIND,
    )


def _child_heads(
    fs: FileSystem, directory: PathArg, container: str, kind: str
) -> list[tuple[str, dict[str, object]]]:
    """``(dir name, frontmatter head)`` of each child record of *kind*, by name."""
    parent = fs.join(directory, container)
    try:
        entries = fs.scandir(parent, with_stat=False)
    except OSError:
        return []
    found: list[tuple[str, dict[str, object]]] = []
    for entry in sorted(entries, key=lambda item: item.name):
        if not entry.is_dir or entry.name.startswith("."):
            continue
        head = frontmatter.read_head(fs, fs.join(parent, entry.name, ENTITY_FILENAME))
        if head and head.get("type") == kind:
            found.append((entry.name, head))
    return found


def _row_path(container: str, name: str) -> str:
    return f"{container}/{name}/{ENTITY_FILENAME}"


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def entrypoint_of(directory: PathArg, canonical: Mapping[str, object]) -> str | None:
    """Where an experiment's workflow lives, as an agent would open it.

    A document workflow is ``workflow.ir.json``. A code workflow is the file
    of its ``"<file>:<qualname>"`` locator, relative to the experiment when
    it is inside it (``workflow.py``) and as recorded otherwise. ``None``
    when the experiment is unbound.
    """
    kind = canonical.get("workflow_kind")
    if kind == "document":
        return _WORKFLOW_DOC
    locator = canonical.get("workflow_entrypoint")
    if not isinstance(locator, str) or not locator:
        return None
    source = locator.rsplit(":", 1)[0] if ":" in locator else locator
    base = posixpath.normpath(str(directory))
    target = posixpath.normpath(source)
    if posixpath.isabs(target) and target.startswith(base.rstrip("/") + "/"):
        return posixpath.relpath(target, base)
    return source


def _workspace_keys(fs: FileSystem, directory: PathArg) -> dict[str, JSONValue]:
    _root, project_kind, _exp, _run = _kinds()
    rows: list[JSONValue] = [
        {
            "name": _text(head.get("name")) or name,
            "path": _row_path(PROJECT_CONTAINER, name),
            "id": _text(head.get("id")),
            "description": _text(head.get("description")),
        }
        for name, head in _child_heads(fs, directory, PROJECT_CONTAINER, project_kind)
    ]
    return {"children": rows}


def _project_keys(fs: FileSystem, directory: PathArg) -> dict[str, JSONValue]:
    _root, _project, experiment_kind, _run = _kinds()
    rows: list[JSONValue] = []
    for name, head in _child_heads(fs, directory, EXPERIMENT_CONTAINER, experiment_kind):
        kind = head.get("workflow_kind")
        rows.append(
            {
                "name": _text(head.get("name")) or name,
                "path": _row_path(EXPERIMENT_CONTAINER, name),
                "id": _text(head.get("id")),
                "description": _text(head.get("description")),
                "workflow_kind": kind if isinstance(kind, str) else None,
                "entrypoint": entrypoint_of(fs.join(directory, EXPERIMENT_CONTAINER, name), head),
            }
        )
    return {"parent": PARENT_INDEX, "children": rows}


def _experiment_keys(
    fs: FileSystem, directory: PathArg, canonical: Mapping[str, object]
) -> dict[str, JSONValue]:
    _root, _project, _exp, run_kind = _kinds()
    rows: list[JSONValue] = []
    for name, head in _child_heads(fs, directory, RUN_CONTAINER, run_kind):
        params = head.get("parameters")
        rows.append(
            {
                "name": name,
                "path": _row_path(RUN_CONTAINER, name),
                "id": _text(head.get("id")),
                "params": cast("JSONValue", params if isinstance(params, dict) else {}),
            }
        )
    return {
        "parent": PARENT_INDEX,
        "entrypoint": entrypoint_of(directory, canonical),
        # No scratch tier is declared yet; the key is emitted so the shape is
        # stable when one is.
        "scratch": False,
        "children": rows,
    }


def _subdir_names(fs: FileSystem, directory: str) -> list[str]:
    try:
        entries = fs.scandir(directory, with_stat=False)
    except OSError:
        return []
    return sorted(e.name for e in entries if e.is_dir and not e.name.startswith("."))


def _job_ids(executor: dict[str, JSONValue]) -> list[JSONValue]:
    """Job ids an executor recorded, in the order it recorded them."""
    found: list[JSONValue] = []
    listed = executor.get("job_ids")
    if isinstance(listed, list):
        found.extend(str(item) for item in listed)
    for key in ("job_id", "scheduler_job_id"):
        value = executor.get(key)
        if value not in (None, "") and str(value) not in found:
            found.append(str(value))
    return found


def _run_keys(fs: FileSystem, directory: PathArg) -> dict[str, JSONValue]:
    from .execution_repository import list_executions

    rows: list[JSONValue] = []
    latest = "pending"
    for state in list_executions(fs, directory):
        dumped = state.model_dump(mode="json", include={"started_at", "finished_at"})
        error = state.error or {}
        error_type = error.get("type")
        attempt = fs.join(directory, "executions", state.id)
        rows.append(
            {
                "id": state.id,
                "path": f"executions/{state.id}",
                "mode": state.mode.value,
                "status": state.status.value,
                "started_at": dumped.get("started_at"),
                "finished_at": dumped.get("finished_at"),
                "job_ids": _job_ids(state.executor),
                "out": list(_subdir_names(fs, fs.join(attempt, _OUT_DIR))),
                "artifacts": [artifact.path for artifact in state.artifacts],
                "error": str(error_type) if error_type else None,
            }
        )
        latest = state.status.value
    return {"parent": PARENT_INDEX, "executions": rows, "latest_status": latest}


def project_index_at(
    fs: FileSystem,
    directory: PathArg,
    kind: str,
    *,
    canonical: Mapping[str, object] | None = None,
) -> dict[str, JSONValue]:
    """The reserved ``index:`` keys of the *kind* level at *directory*.

    Args:
        fs: The disk.
        directory: The level's directory.
        kind: Its record ``type``; any other kind has no reserved keys.
        canonical: The level's own canonical zone, when the caller has it
            (an experiment's ``entrypoint`` is read from it).
    """
    root_kind, project_kind, experiment_kind, run_kind = _kinds()
    if kind == root_kind:
        return _workspace_keys(fs, directory)
    if kind == project_kind:
        return _project_keys(fs, directory)
    if kind == experiment_kind:
        own = canonical
        if own is None:
            own = frontmatter.read_head(fs, fs.join(directory, ENTITY_FILENAME)) or {}
        return _experiment_keys(fs, directory, own)
    if kind == run_kind:
        return _run_keys(fs, directory)
    return {}


def project_index(folder: Folder) -> dict[str, JSONValue]:
    """The reserved ``index:`` keys for *folder*'s level, built from the tree."""
    return project_index_at(folder._disk(), folder.resolve(), folder.kind)


def merge_reserved(
    index: dict[str, JSONValue], reserved: dict[str, JSONValue]
) -> dict[str, JSONValue]:
    """*index* with its reserved keys replaced by *reserved*; other keys kept verbatim."""
    merged: dict[str, JSONValue] = {key: reserved[key] for key in _ORDER if key in reserved}
    merged.update({key: value for key, value in index.items() if key not in RESERVED_INDEX_KEYS})
    return merged


def refresh_index_at(
    fs: FileSystem,
    directory: PathArg,
    *,
    lock_root: PathArg | None = None,
) -> None:
    """Rewrite the reserved keys of the record at *directory*, in place.

    The projection runs inside the record's lock, so two writers refreshing
    the same parent cannot leave a stale row behind. A directory with no
    record is left alone; nothing is written when nothing changed.
    """

    def change(current: EntityRecord) -> EntityRecord:
        if not current.type:
            return current
        reserved = project_index_at(fs, directory, current.type, canonical=current.canonical)
        merged = merge_reserved(current.index, reserved)
        if merged == current.index:
            return current
        return EntityRecord(canonical=current.canonical, index=merged, body=current.body)

    update_record(fs, directory, change, lock_root=lock_root)


def _lock_root(folder: Folder) -> PathArg:
    return folder.asset_host().resolve()


def refresh_index(folder: Folder, *, parent: bool = True) -> None:
    """Rewrite *folder*'s reserved ``index:`` keys and, with *parent*, its parent's.

    Never raises: a failure is logged and the caller carries on.
    """
    try:
        refresh_index_at(folder._disk(), folder.resolve(), lock_root=_lock_root(folder))
        up = folder.parent
        if parent and up is not None:
            refresh_index_at(up._disk(), up.resolve(), lock_root=_lock_root(up))
    except Exception as exc:
        _logger.warning(f"index refresh failed for {folder.kind} {folder.name!r}: {exc}")


def refresh_run_index(fs: FileSystem, run_dir: PathArg, *, lock_root: PathArg | None) -> None:
    """Rewrite one run's reserved keys (the attempt list); never its parent's.

    Called by the Execution owner after it writes an attempt record. Never
    raises.
    """
    try:
        refresh_index_at(fs, run_dir, lock_root=lock_root)
    except Exception as exc:
        _logger.warning(f"index refresh failed for run {run_dir}: {exc}")


def sync_index(folder: Folder) -> int:
    """Rebuild every reserved key under *folder*, bottom-up. Returns records visited.

    The full rebuild ``molab index sync`` and ``molab migrate index`` run.
    Children are refreshed before their parent, so a parent row reads the
    child's final head.
    """
    fs = folder._disk()
    lock_root = _lock_root(folder)
    root_kind, project_kind, experiment_kind, _run_kind = _kinds()
    containers = {
        root_kind: PROJECT_CONTAINER,
        project_kind: EXPERIMENT_CONTAINER,
        experiment_kind: RUN_CONTAINER,
    }
    visited = 0

    def walk(directory: str, kind: str) -> None:
        nonlocal visited
        container = containers.get(kind)
        if container is not None:
            child_kind = {
                root_kind: project_kind,
                project_kind: experiment_kind,
                experiment_kind: _run_kind,
            }[kind]
            for name, _head in _child_heads(fs, directory, container, child_kind):
                walk(fs.join(directory, container, name), child_kind)
        refresh_index_at(fs, directory, lock_root=lock_root)
        visited += 1

    walk(str(folder.resolve()), folder.kind)
    return visited


__all__ = [
    "PARENT_INDEX",
    "entrypoint_of",
    "merge_reserved",
    "project_index",
    "project_index_at",
    "refresh_index",
    "refresh_index_at",
    "refresh_run_index",
    "sync_index",
]
