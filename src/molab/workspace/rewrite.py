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
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import cast

from pydantic import BaseModel, ValidationError

from molab._typing import JSONValue
from molab.ids import generate_uuid7

from .asset_repository import asset_slug, content_ref
from .base import _load_metadata, _record_payload
from .domain import Asset, AssetOrigin, AssetScope, ExecutionOrigin, ImportOrigin
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
from .history import SYSTEM_AGENT, AgentRef
from .models import ExperimentMetadata, ProjectMetadata, RunMetadata, WorkspaceMetadata
from .naming import (
    ASSET_CONTAINER,
    EXECUTION_CONTAINER,
    EXPERIMENT_CONTAINER,
    PROJECT_CONTAINER,
    RUN_CONTAINER,
)
from .run import compute_run_definition_hash
from .schema_version import versioned_payload

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

    Then every current asset is moved into its slot (``<run>--<title>`` for an
    attempt's product, ``<title>`` for an import): of several assets that
    share a slot the newest attempt's wins and the rest are deleted, and a
    registered log is deleted.

    After the records match, each kept file that still lives in a version
    directory or in an attempt's old product directory is registered as a new
    asset. The old id is not reused. A metrics log is moved beside
    ``execution.json`` and is not registered. The version directory and the
    old product directory are removed once the bytes have a new home.

    Args:
        root: Workspace root. May be a path that does not exist yet.
        fs: Filesystem to read and write. A local disk when omitted.
        name: Display name used when the root record has none.
    """
    disk = fs or LocalFS()
    root_s = str(root)
    if not disk.is_dir(root_s):
        return
    digests: set[str] = set()
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
                run_dir = disk.join(runs, run_name)
                _rewrite_level(
                    disk,
                    run_dir,
                    "run",
                    run_name,
                    lock_root=root_s,
                    revision_id=revision_id,
                )
                _remint_attempt_products(
                    disk,
                    root_s,
                    project_dir=project_dir,
                    experiment_dir=experiment_dir,
                    run_dir=run_dir,
                    digests=digests,
                )
            experiment_id = _text(_canonical(disk, experiment_dir).get("id"))
            project_id = _text(_canonical(disk, project_dir).get("id"))
            if project_id and experiment_id:
                _remint_scope_assets(
                    disk,
                    root_s,
                    experiment_dir,
                    AssetScope(kind="experiment", ids=(project_id, experiment_id)),
                    digests,
                )
            run_names = {
                _text(_canonical(disk, disk.join(runs, name)).get("id")): name
                for name in _child_dirs(disk, runs)
            }
            _reslot_scope_assets(disk, experiment_dir, run_names)
        project_id = _text(_canonical(disk, project_dir).get("id"))
        if project_id:
            _remint_scope_assets(
                disk,
                root_s,
                project_dir,
                AssetScope(kind="project", ids=(project_id,)),
                digests,
            )
        _reslot_scope_assets(disk, project_dir, {})
    _remint_scope_assets(disk, root_s, root_s, AssetScope(kind="workspace", ids=()), digests)
    _reslot_scope_assets(disk, root_s, {})


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
    had_revision = bool(_text(source.get("experiment_revision_id")))
    had_hash = _text(source.get("definition_hash")) not in {"", "sha256:pending"}
    metadata = _build(model, source, kind=kind, fallback_name=fallback_name)
    if isinstance(metadata, ExperimentMetadata):
        metadata = _with_experiment_hash(fs, directory, metadata)
    elif isinstance(metadata, RunMetadata):
        metadata = _with_run_hash(
            metadata,
            revision_id,
            had_revision=had_revision,
            had_hash=had_hash,
        )
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


def _with_run_hash(
    metadata: RunMetadata,
    revision_id: str,
    *,
    had_revision: bool,
    had_hash: bool,
) -> RunMetadata:
    """Fill a missing revision citation or a missing definition hash.

    A run that already has a hash keeps that hash and, when it also cited a
    revision, that citation. Recomputing would drop the profile
    ``config_hash``, which is not stored beside the hash. A legacy run with
    no hash cites the experiment revision this rewrite just wrote.
    """
    if had_hash:
        if had_revision:
            return metadata
        parent = revision_id or metadata.experiment_revision_id
        return metadata.model_copy(update={"experiment_revision_id": parent})
    parent = revision_id or metadata.experiment_revision_id
    digest = compute_run_definition_hash(
        experiment_revision_id=parent,
        parameters=metadata.parameters,
        input_asset_ids=metadata.inputs,
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


_LEGACY_PRODUCT_DIR = "artifacts"
"""Attempt directory init still clears. New attempts do not create it."""


def _remint_attempt_products(
    fs: FileSystem,
    root: str,
    *,
    project_dir: str,
    experiment_dir: str,
    run_dir: str,
    digests: set[str],
) -> None:
    """Register bytes listed on an attempt, then remove the old product directory."""
    executions = fs.join(run_dir, EXECUTION_CONTAINER)
    project_id = _text(_canonical(fs, project_dir).get("id"))
    experiment_id = _text(_canonical(fs, experiment_dir).get("id"))
    run_id = _text(_canonical(fs, run_dir).get("id"))
    scope = (
        AssetScope(kind="experiment", ids=(project_id, experiment_id))
        if project_id and experiment_id
        else None
    )
    for name in _child_dirs(fs, executions):
        execution_dir = fs.join(executions, name)
        record_path = fs.join(execution_dir, "execution.json")
        raw = _read_object(fs, record_path)
        if not raw:
            continue
        execution_id = _text(raw.get("id")) or name
        listed = raw.get(_LEGACY_PRODUCT_DIR)
        items = listed if isinstance(listed, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            location = _legacy_location(fs, root, execution_dir, item.get("path"))
            if location is None:
                continue
            if _is_metrics(location):
                _move_metrics(fs, execution_dir, location)
                continue
            task = item.get("metadata")
            task_name = task.get("task_id") if isinstance(task, dict) else None
            if scope is not None and run_id:
                origin: AssetOrigin = ExecutionOrigin(
                    project_id=project_id,
                    experiment_id=experiment_id,
                    run_id=run_id,
                    execution_id=execution_id,
                    task=task_name if isinstance(task_name, str) else None,
                )
                home = experiment_dir
                home_scope = scope
            else:
                origin = ImportOrigin(uri=location)
                home = root
                home_scope = AssetScope(kind="workspace", ids=())
            _mint_asset(
                fs,
                home,
                home_scope,
                source=location,
                title=_text(item.get("name")) or "asset",
                media_type=_text(item.get("media_type")) or None,
                origin=origin,
                created_by=_agent(item.get("created_by")),
                digests=digests,
                run_name=PurePosixPath(run_dir).name,
            )
        changed = False
        for key in ("artifacts", "checkpoint_artifact_id", "observed_input_ids", "sealed_commit"):
            if key in raw:
                raw.pop(key)
                changed = True
        if changed:
            fs.atomic_write_json(record_path, raw)
        product_dir = fs.join(execution_dir, _LEGACY_PRODUCT_DIR)
        if fs.is_dir(product_dir):
            for entry in fs.ls(product_dir, A=True):
                nested = fs.join(product_dir, entry)
                if _is_metrics(nested) and fs.is_file(nested):
                    _move_metrics(fs, execution_dir, nested)
            fs.rm(product_dir, recursive=True)


def _remint_scope_assets(
    fs: FileSystem,
    root: str,
    scope_dir: str,
    scope: AssetScope,
    digests: set[str],
) -> None:
    """Mint one asset per file still stored as a version, then delete that record."""
    assets_dir = fs.join(scope_dir, ASSET_CONTAINER)
    if not fs.is_dir(assets_dir):
        return
    names = [
        name
        for name in fs.ls(assets_dir, A=True)
        if fs.is_dir(fs.join(assets_dir, name)) and not name.startswith(".")
    ]
    for name in names:
        directory = fs.join(assets_dir, name)
        raw = _read_object(fs, fs.join(directory, "asset.json"))
        if raw and not _legacy_asset(fs, directory, raw):
            content = raw.get("content")
            digest = content.get("digest") if isinstance(content, dict) else None
            if isinstance(digest, str):
                digests.add(digest)
    for name in names:
        directory = fs.join(assets_dir, name)
        record = fs.join(directory, "asset.json")
        raw = _read_object(fs, record)
        if not _legacy_asset(fs, directory, raw):
            continue
        title = _text(raw.get("title")) or _text(raw.get("name")) or name
        created_by = _agent(raw.get("created_by"))
        minted: set[str] = set()
        for source, media_type in _legacy_payloads(fs, root, scope_dir, directory, raw):
            if not fs.exists(source):
                continue
            home = _mint_asset(
                fs,
                scope_dir,
                scope,
                source=source,
                title=title,
                media_type=media_type,
                origin=ImportOrigin(uri=source),
                created_by=created_by,
                digests=digests,
            )
            if home is not None:
                minted.add(home)
        if directory not in minted and fs.exists(directory):
            fs.rm(directory, recursive=True)


def _legacy_asset(fs: FileSystem, directory: str, raw: dict[str, object]) -> bool:
    if fs.is_dir(fs.join(directory, "versions")):
        return True
    if not fs.is_file(fs.join(directory, "asset.json")):
        return False
    return "origin" not in raw


def _legacy_payloads(
    fs: FileSystem,
    root: str,
    scope_dir: str,
    directory: str,
    raw: dict[str, object],
) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    def add(location: str | None, media_type: str | None) -> None:
        if location is None or location in seen:
            return
        seen.add(location)
        found.append((location, media_type))

    add(_legacy_location(fs, root, scope_dir, raw.get("path")), None)
    versions = fs.join(directory, "versions")
    if fs.is_dir(versions):
        for name in fs.ls(versions, A=True):
            if not name.endswith(".json"):
                continue
            version = _read_object(fs, fs.join(versions, name))
            origin = version.get("origin")
            hinted = None
            if isinstance(origin, dict):
                hinted = origin.get("location") or origin.get("uri")
            media = _text(version.get("media_type")) or None
            add(_legacy_location(fs, root, scope_dir, version.get("path") or hinted), media)
    if fs.is_dir(directory):
        for name in fs.ls(directory, A=True):
            path = fs.join(directory, name)
            if name == "asset.json" or not fs.is_file(path):
                continue
            add(path, None)
    return found


def _legacy_location(fs: FileSystem, root: str, base: str, value: object) -> str | None:
    text = _text(value)
    if not text or ".." in PurePosixPath(text).parts:
        return None
    candidates = [text]
    if not text.startswith("/"):
        candidates.append(fs.join(root, text))
        candidates.append(fs.join(base, text))
    for candidate in candidates:
        if fs.is_file(candidate) or fs.is_dir(candidate):
            return candidate
    return None


def _mint_asset(
    fs: FileSystem,
    scope_dir: str,
    scope: AssetScope,
    *,
    source: str,
    title: str,
    media_type: str | None,
    origin: AssetOrigin,
    created_by: AgentRef,
    digests: set[str],
    run_name: str | None = None,
) -> str | None:
    """Mint one asset in its slot and return its directory. A later attempt's bytes replace an earlier one's; logs are dropped."""
    if not fs.is_file(source) and not fs.is_dir(source):
        return None
    if fs.is_file(source) and PurePosixPath(source).suffix.lower() == ".log":
        return None
    content = content_ref(fs, source)
    assets_dir = fs.join(scope_dir, ASSET_CONTAINER)
    slug = asset_slug(title, run_name if isinstance(origin, ExecutionOrigin) else None)
    asset_root = fs.join(assets_dir, slug)
    previous = _read_object(fs, fs.join(asset_root, "asset.json"))
    if content.digest in digests:
        old_content = previous.get("content") if previous else None
        same_slot = isinstance(old_content, dict) and old_content.get("digest") == content.digest
        if same_slot and "origin" in previous:
            # A later attempt made the same bytes: it is now the slot's producer.
            previous["origin"] = origin.model_dump(mode="json")
            fs.atomic_write_json(fs.join(asset_root, "asset.json"), previous)
            return asset_root
        return None
    fs.mkdir(assets_dir, parents=True, exist_ok=True)
    asset_id = generate_uuid7()
    if previous and "origin" in previous and not fs.is_dir(fs.join(asset_root, "versions")):
        asset_id = _text(previous.get("id")) or asset_id
        old_content = previous.get("content")
        if isinstance(old_content, dict):
            digests.discard(_text(old_content.get("digest")))
    staged: str | None = None
    if fs.exists(asset_root):
        if PurePosixPath(source).is_relative_to(PurePosixPath(asset_root)):
            staged = fs.join(assets_dir, f".mint-{asset_id}{PurePosixPath(source).suffix}")
            fs.cp(source, staged, recursive=fs.is_dir(source))
            source = staged
        fs.rm(asset_root, recursive=True)
    filename = f"payload{PurePosixPath(source).suffix}" if fs.is_file(source) else "payload"
    fs.mkdir(asset_root, parents=True, exist_ok=True)
    fs.cp(source, fs.join(asset_root, filename), recursive=fs.is_dir(source))
    if staged is not None:
        fs.rm(staged, recursive=fs.is_dir(staged))
    asset = Asset(
        id=asset_id,
        scope=scope,
        title=title,
        content=content,
        media_type=media_type,
        origin=origin,
        file=filename,
        created_at=datetime.now(UTC),
        created_by=created_by,
        tags={},
    )
    fs.atomic_write_json(
        fs.join(asset_root, "asset.json"),
        versioned_payload(asset.model_dump(mode="json")),
    )
    digests.add(content.digest)
    return asset_root


def _reslot_scope_assets(fs: FileSystem, scope_dir: str, run_names: dict[str, str]) -> None:
    """Move each current asset under *scope_dir* into its slot; drop logs and losers."""
    from .naming import parse_execution_seq

    assets_dir = fs.join(scope_dir, ASSET_CONTAINER)
    if not fs.is_dir(assets_dir):
        return
    claims: dict[str, list[tuple[tuple[int, str], str]]] = {}
    for name in _child_dirs(fs, assets_dir):
        directory = fs.join(assets_dir, name)
        raw = _read_object(fs, fs.join(directory, "asset.json"))
        origin = raw.get("origin")
        if not isinstance(origin, dict) or fs.is_dir(fs.join(directory, "versions")):
            continue
        title = _text(raw.get("title")) or name
        if title.lower().endswith(".log") or _text(raw.get("file")).lower().endswith(".log"):
            fs.rm(directory, recursive=True)
            continue
        if origin.get("kind") == "execution":
            run_id = _text(origin.get("run_id"))
            if run_id not in run_names:
                raise ValueError(
                    f"asset {directory} was produced by run {run_id!r}, which no run "
                    f"directory under {scope_dir} records"
                )
            slot = asset_slug(title, run_names[run_id])
            rank = (
                parse_execution_seq(_text(origin.get("execution_id"))) or 0,
                _text(raw.get("created_at")),
            )
        else:
            slot = asset_slug(title)
            rank = (0, _text(raw.get("created_at")))
        claims.setdefault(slot, []).append((rank, name))
    staged: list[tuple[str, str]] = []
    for slot, contenders in claims.items():
        contenders.sort()
        *losers, (_, winner) = contenders
        for _, name in losers:
            fs.rm(fs.join(assets_dir, name), recursive=True)
        if winner != slot:
            # Two phases, so a winner never lands on a directory another
            # asset still has to leave.
            temporary = fs.join(assets_dir, f".reslot-{slot}")
            fs.mv(fs.join(assets_dir, winner), temporary)
            staged.append((temporary, fs.join(assets_dir, slot)))
    for temporary, target in staged:
        fs.mv(temporary, target)


def _move_metrics(fs: FileSystem, execution_dir: str, source: str) -> None:
    dest = fs.join(execution_dir, PurePosixPath(source).name)
    if fs.exists(dest) or not fs.is_file(source):
        return
    fs.cp(source, dest)


def _is_metrics(path: str) -> bool:
    return PurePosixPath(path).name.endswith(".mlp.jsonl")


def _agent(value: object) -> AgentRef:
    if isinstance(value, dict):
        try:
            return AgentRef.model_validate(value)
        except ValidationError:
            return SYSTEM_AGENT
    return SYSTEM_AGENT


__all__ = ["rewrite_records"]
