"""Rewrite a workspace's records into the current ``index.md`` format.

``molab init`` is the only caller. Readers still refuse a directory that has a
legacy JSON record and no current ``index.md`` record; they do not upgrade it.
This module does the upgrade once: a meta file or a record that does not match
the current model is replaced, and the meta file is deleted. A record that
already validates is kept, including its id and its narrative. The derived
``index:`` block is rebuilt afterwards by the caller.
"""

from __future__ import annotations

import json
from typing import cast

from pydantic import BaseModel, ValidationError

from molab._typing import JSONValue
from molab.ids import generate_uuid7

from .base import _load_metadata, _record_payload
from .entity_record import (
    INDEX_KEY,
    LEGACY_RECORD_FILES,
    read_type,
    write_record,
)
from .experiment import _experiment_definition_hash
from .folder import (
    WORKSPACE_EXPERIMENT_KIND,
    WORKSPACE_PROJECT_KIND,
    WORKSPACE_ROOT_KIND,
    WORKSPACE_RUN_KIND,
)
from .fs import FileSystem, PathArg
from .fs_local import LocalFS
from .models import ExperimentMetadata, ProjectMetadata, RunMetadata, WorkspaceMetadata
from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER
from .run import compute_run_definition_hash

_LEVELS: dict[str, tuple[str, type[BaseModel], str]] = {
    "workspace": (WORKSPACE_ROOT_KIND, WorkspaceMetadata, "workspace.json"),
    "project": (WORKSPACE_PROJECT_KIND, ProjectMetadata, "project.json"),
    "experiment": (WORKSPACE_EXPERIMENT_KIND, ExperimentMetadata, "experiment.json"),
    "run": (WORKSPACE_RUN_KIND, RunMetadata, "run.json"),
}


def rewrite_records(
    root: PathArg, *, fs: FileSystem | None = None, name: str | None = None
) -> None:
    """Rewrite *root* and its project, experiment and run records.

    A missing directory is left untouched (a new workspace has nothing to
    adopt). ``__pycache__`` and dot-directories are not records. A ``meta.json``
    under ``scratch/`` or an attempt directory is science payload and is not
    touched; only the entity directory's own meta file is.

    Args:
        root: Workspace root. May be a path that does not exist yet.
        fs: Filesystem to read and write. A local disk when omitted.
        name: Display name used when the root record has none.
    """
    disk = fs or LocalFS()
    root_s = str(root)
    if not disk.is_dir(root_s):
        return
    _rewrite_level(disk, root_s, "workspace", name or disk.basename(root_s), lock_root=root_s)
    for project_name in _child_dirs(disk, disk.join(root_s, PROJECT_CONTAINER)):
        project_dir = disk.join(root_s, PROJECT_CONTAINER, project_name)
        _rewrite_level(disk, project_dir, "project", project_name, lock_root=root_s)
        experiments = disk.join(project_dir, EXPERIMENT_CONTAINER)
        for experiment_name in _child_dirs(disk, experiments):
            experiment_dir = disk.join(experiments, experiment_name)
            _rewrite_level(disk, experiment_dir, "experiment", experiment_name, lock_root=root_s)
            revision_id = _text(_canonical(disk, experiment_dir).get("revision_id"))
            runs = disk.join(experiment_dir, RUN_CONTAINER)
            for run_name in _child_dirs(disk, runs):
                _rewrite_level(
                    disk,
                    disk.join(runs, run_name),
                    "run",
                    run_name,
                    lock_root=root_s,
                    revision_id=revision_id,
                )


def _rewrite_level(
    fs: FileSystem,
    directory: str,
    level: str,
    fallback_name: str,
    *,
    lock_root: str,
    revision_id: str = "",
) -> None:
    kind, model, level_file = _LEVELS[level]
    if _current(fs, directory, model, kind):
        _delete_legacy(fs, directory)
        return
    source = _source(fs, directory, level_file)
    metadata = _build(model, source, kind=kind, fallback_name=fallback_name)
    if isinstance(metadata, ExperimentMetadata):
        metadata = _with_experiment_hash(fs, directory, metadata)
    elif isinstance(metadata, RunMetadata):
        metadata = _with_run_hash(metadata, revision_id)
    write_record(fs, directory, canonical=_record_payload(metadata), lock_root=lock_root)
    _delete_legacy(fs, directory)


def _current(fs: FileSystem, directory: str, model: type[BaseModel], kind: str) -> bool:
    if read_type(fs, directory) != kind:
        return False
    try:
        _load_metadata(model, _canonical(fs, directory))
    except ValidationError:
        return False
    return True


def _build[ModelT: BaseModel](
    model: type[ModelT], source: dict[str, object], *, kind: str, fallback_name: str
) -> ModelT:
    """A current *model*. Fields that do not fit are dropped, not reinterpreted."""
    data = {key: value for key, value in source.items() if key in model.model_fields}
    _fill_required(model, data, kind=kind, fallback_name=fallback_name)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            loc = err.get("loc") or ()
            if loc:
                data.pop(str(loc[0]), None)
        _fill_required(model, data, kind=kind, fallback_name=fallback_name)
        return model.model_validate(data)


def _fill_required(
    model: type[BaseModel], data: dict[str, object], *, kind: str, fallback_name: str
) -> None:
    data["type"] = kind
    if not _text(data.get("id")):
        data["id"] = generate_uuid7()
    if "name" in model.model_fields and not _text(data.get("name")):
        data["name"] = fallback_name
    if model is ExperimentMetadata and not _text(data.get("revision_id")):
        data["revision_id"] = generate_uuid7()
    if model is ExperimentMetadata and not _text(data.get("definition_hash")):
        data["definition_hash"] = "sha256:pending"
    if model is RunMetadata and not _text(data.get("definition_hash")):
        data["definition_hash"] = "sha256:pending"
    if model is RunMetadata and not _text(data.get("experiment_revision_id")):
        data["experiment_revision_id"] = generate_uuid7()


def _with_experiment_hash(
    fs: FileSystem, directory: str, metadata: ExperimentMetadata
) -> ExperimentMetadata:
    document = _workflow_document(fs, directory, metadata)
    digest = _experiment_definition_hash(metadata.model_dump(), document=document)
    return metadata.model_copy(update={"definition_hash": digest})


def _with_run_hash(metadata: RunMetadata, revision_id: str) -> RunMetadata:
    """A rewritten run cites the experiment revision just written."""
    parent = revision_id or metadata.experiment_revision_id
    digest = compute_run_definition_hash(
        experiment_revision_id=parent,
        parameters=metadata.parameters,
        input_asset_ids=metadata.input_asset_ids,
    )
    return metadata.model_copy(update={"experiment_revision_id": parent, "definition_hash": digest})


def _workflow_document(
    fs: FileSystem, directory: str, metadata: ExperimentMetadata
) -> dict[str, JSONValue] | None:
    if metadata.workflow_kind != "document":
        return None
    loaded = _read_object(fs, fs.join(directory, "workflow.ir.json"))
    if not loaded:
        return None
    return cast(dict[str, JSONValue], loaded)


def _source(fs: FileSystem, directory: str, level_file: str) -> dict[str, object]:
    """Legacy JSON, then the ``index.md`` head. The head wins when both exist."""
    source: dict[str, object] = {}
    for name in ("meta.json", level_file):
        source.update(_read_object(fs, fs.join(directory, name)))
    source.update(_canonical(fs, directory))
    source.pop("schema_version", None)
    return source


def _canonical(fs: FileSystem, directory: str) -> dict[str, object]:
    from molab import frontmatter

    text = _read_text(fs, fs.join(directory, "index.md"))
    if text is None:
        return {}
    meta, _body = frontmatter.split(text)
    return {key: value for key, value in meta.items() if key != INDEX_KEY}


def _read_object(fs: FileSystem, path: str) -> dict[str, object]:
    text = _read_text(fs, path)
    if text is None:
        return {}
    try:
        loaded = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): value for key, value in loaded.items()}


def _read_text(fs: FileSystem, path: str) -> str | None:
    if not fs.is_file(path):
        return None
    try:
        return fs.read_text(path)
    except OSError:
        return None


def _delete_legacy(fs: FileSystem, directory: str) -> None:
    for name in LEGACY_RECORD_FILES:
        path = fs.join(directory, name)
        if fs.is_file(path):
            fs.rm(path)


def _child_dirs(fs: FileSystem, container: str) -> list[str]:
    if not fs.is_dir(container):
        return []
    try:
        entries = fs.ls(container, A=True, l=True)
    except OSError:
        return []
    return [
        entry.name
        for entry in sorted(entries, key=lambda item: item.name)
        if entry.is_dir and not entry.name.startswith(".") and entry.name != "__pycache__"
    ]


def _text(value: object) -> str:
    return value if isinstance(value, str) and value.strip() else ""


__all__ = ["rewrite_records"]
