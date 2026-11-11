"""Scope-level assets: one registered file, one id, one ref.

Records live at ``<scope>/assets/<slug>/asset.json``. The bytes sit beside
the record (``payload`` plus the source suffix). A second registration of
the same digest returns the existing asset.

One asset per slot. A slot is the title within its scope, and, for bytes an
attempt produced, the run as well: ``<run>--<title>``. Registering a slot
again with other bytes replaces it in place and keeps its id, so a citation
names "this run's network.data", never a stale attempt's copy. Slugs never
grow ``-2`` suffixes. Logs are not products and are refused.
"""

from __future__ import annotations

import builtins
import contextlib
import hashlib
import json
import re
import shutil
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from molab.ids import generate_uuid7

from ._file_lock import file_lock
from .domain import Asset, AssetOrigin, AssetScope, ContentRef, ExecutionOrigin, ImportOrigin
from .errors import UnmigratedAssetError
from .fs import FileSystem, PathArg
from .fs_local import LocalFS
from .history import MOLAB_DIR, AgentRef
from .naming import ASSET_CONTAINER
from .schema_version import versioned_payload

if TYPE_CHECKING:
    from .workspace import Workspace


def _hash_file(fs: FileSystem, path: str) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with fs.open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return f"sha256:{hasher.hexdigest()}", size


def _hash_tree(fs: FileSystem, path: str) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    prefix = path.rstrip("/") + "/"
    for entry in sorted(item for item in fs.rglob(path, "*") if fs.is_file(item)):
        rel = entry[len(prefix) :] if entry.startswith(prefix) else fs.basename(entry)
        hasher.update(PurePosixPath(rel).as_posix().encode() + b"\0")
        with fs.open(entry, "rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
        hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}", size


def content_ref(fs: FileSystem, path: PathArg) -> ContentRef:
    """Identify bytes where they already live."""
    target = str(path)
    if fs.is_dir(target):
        digest, size = _hash_tree(fs, target)
        return ContentRef(digest=digest, size=size, kind="directory")
    digest, size = _hash_file(fs, target)
    return ContentRef(digest=digest, size=size, kind="file")


def _digest_local(path: Path) -> ContentRef:
    """Hash a local path the workspace filesystem may not own yet."""
    if path.is_dir():
        hasher = hashlib.sha256()
        size = 0
        for entry in sorted(item for item in path.rglob("*") if item.is_file()):
            rel = entry.relative_to(path).as_posix()
            hasher.update(rel.encode() + b"\0")
            with entry.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
            hasher.update(b"\0")
        return ContentRef(digest=f"sha256:{hasher.hexdigest()}", size=size, kind="directory")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return ContentRef(digest=f"sha256:{hasher.hexdigest()}", size=size, kind="file")


_EVIDENCE_SUFFIXES = frozenset({".log"})


def _slug_part(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def run_slot_prefix(run_name: str) -> str:
    """Slug prefix every product slot of run *run_name* starts with: ``<run>--``."""
    run_part = _slug_part(run_name)
    if not run_part:
        raise ValueError(f"run name {run_name!r} has no slug characters")
    return f"{run_part}--"


def asset_slug(title: str, run_name: str | None = None) -> str:
    """Directory name of an asset slot: ``<title>``, or ``<run>--<title>`` for a run's product."""
    title_part = _slug_part(title) or "asset"
    if run_name is None:
        return title_part
    return f"{run_slot_prefix(run_name)}{title_part}"


def scan_asset_repositories(workspace: Workspace) -> builtins.list[AssetRepository]:
    """Every asset host in *workspace*, in tree order.

    Workspace first, then each project, then each of that project's
    experiments. Runs are not hosts. A directory with no ``index.md`` record
    is skipped.
    """
    from molab import frontmatter

    from .entity_record import ENTITY_FILENAME
    from .folder import WORKSPACE_EXPERIMENT_KIND, WORKSPACE_PROJECT_KIND
    from .naming import EXPERIMENT_CONTAINER, PROJECT_CONTAINER, RUN_CONTAINER
    from .workspace import Workspace as WorkspaceCls

    def _entity_id(directory: str, kind: str) -> str | None:
        head = frontmatter.read_head(workspace.fs, workspace.fs.join(directory, ENTITY_FILENAME))
        if not head or head.get("type") != kind:
            return None
        found = head.get("id")
        return found if isinstance(found, str) else None

    repos: list[AssetRepository] = []
    root = str(workspace.root)
    for host in WorkspaceCls.list_hosts(workspace.root, fs=workspace.fs):
        host_s = str(host)
        if host_s == root:
            # A served run is not an asset host. Its products live on the experiment.
            if PurePosixPath(host_s).parent.name == RUN_CONTAINER:
                continue
            repos.append(workspace.assets)
            continue
        parent_name = PurePosixPath(host_s).parent.name
        if parent_name == RUN_CONTAINER:
            continue
        if parent_name == PROJECT_CONTAINER:
            project_id = _entity_id(host_s, WORKSPACE_PROJECT_KIND)
            if project_id is None:
                continue
            repos.append(
                AssetRepository(
                    workspace,
                    AssetScope(kind="project", ids=(project_id,)),
                    host_s,
                )
            )
            continue
        if parent_name == EXPERIMENT_CONTAINER:
            experiment_id = _entity_id(host_s, WORKSPACE_EXPERIMENT_KIND)
            project_dir = str(PurePosixPath(host_s).parent.parent)
            project_id = _entity_id(project_dir, WORKSPACE_PROJECT_KIND)
            if experiment_id is None or project_id is None:
                continue
            repos.append(
                AssetRepository(
                    workspace,
                    AssetScope(kind="experiment", ids=(project_id, experiment_id)),
                    host_s,
                )
            )
    return repos


def _legacy_origin(raw: dict) -> ImportOrigin | ExecutionOrigin:
    kind = raw.get("kind")
    if kind == "import":
        uri = raw.get("uri")
        if not isinstance(uri, str) or not uri:
            raise ValueError("legacy import origin has no uri")
        return ImportOrigin(uri=uri)
    if kind == "execution":
        return ExecutionOrigin.model_validate(
            {
                key: raw.get(key)
                for key in ("project_id", "experiment_id", "run_id", "execution_id", "task")
            }
        )
    raise ValueError(f"legacy origin kind {kind!r} is not import or execution")


def migrate_legacy_assets(workspace: Workspace) -> builtins.list[Asset]:
    """Rewrite every versioned asset record in *workspace*. See :meth:`AssetRepository.migrate_legacy`."""
    migrated: list[Asset] = []
    for repository in scan_asset_repositories(workspace):
        migrated.extend(repository.migrate_legacy())
    return migrated


def asset_by_digest(workspace: Workspace, digest: str) -> Asset | None:
    """The one asset in *workspace* whose content digest is *digest*."""
    found: list[Asset] = []
    for repository in scan_asset_repositories(workspace):
        for asset in repository.list():
            if asset.content.digest == digest:
                found.append(asset)
    if not found:
        return None
    if len(found) > 1:
        ids = ", ".join(asset.id for asset in found)
        raise ValueError(f"content digest {digest} is stored as more than one asset ({ids})")
    return found[0]


def assets_produced_by(workspace: Workspace, execution_id: str) -> builtins.list[Asset]:
    """Assets whose origin is attempt *execution_id*."""
    found: list[Asset] = []
    for repository in scan_asset_repositories(workspace):
        for asset in repository.list():
            origin = asset.origin
            if isinstance(origin, ExecutionOrigin) and origin.execution_id == execution_id:
                found.append(asset)
    return found


def asset_by_id(workspace: Workspace, asset_id: str) -> Asset | None:
    """The one asset in *workspace* with id *asset_id*."""
    found: list[Asset] = []
    for repository in scan_asset_repositories(workspace):
        try:
            found.append(repository.get(asset_id))
        except KeyError:
            continue
    if not found:
        return None
    if len(found) > 1:
        places = ", ".join(asset.scope.urn for asset in found)
        raise ValueError(f"asset id {asset_id} exists in more than one scope ({places})")
    return found[0]


def payload_path_for(workspace: Workspace, asset_id: str) -> str:
    """Filesystem path of asset *asset_id*, checked against its digest.

    Raises:
        KeyError: No asset has that id.
    """
    asset = asset_by_id(workspace, asset_id)
    if asset is None:
        raise KeyError(asset_id)
    return workspace.assets_at(asset.scope).payload_path(asset.id)


class AssetRepository:
    """Assets owned by one workspace, project, or experiment."""

    def __init__(
        self,
        workspace: Workspace,
        scope: AssetScope,
        scope_dir: PathArg,
    ) -> None:
        self.workspace = workspace
        self.root = str(workspace.resolve())
        self.scope = scope
        self.scope_dir = str(scope_dir)
        self.fs = workspace.fs

    @property
    def assets_dir(self) -> str:
        return self.fs.join(self.scope_dir, ASSET_CONTAINER)

    def register(
        self,
        source: str | Path,
        *,
        title: str,
        created_by: AgentRef,
        origin: AssetOrigin,
        media_type: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Asset:
        """Register *source* in its slot, or return the asset that already holds those bytes.

        The slot is *title* in this scope, plus the run's directory name when
        *origin* is an attempt. New bytes in an occupied slot replace the old ones in place
        and keep the asset id. Bytes already stored anywhere in the workspace
        return that asset, and a stale asset in this slot is removed.

        Raises:
            FileNotFoundError: *source* does not exist.
            ValueError: *source* is a log, or another slot already owns the slug.
            UnmigratedAssetError: This scope still holds a versioned record.
        """
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")
        if path.is_file() and path.suffix.lower() in _EVIDENCE_SUFFIXES:
            raise ValueError(
                f"{path.name} is a log: logs are evidence and stay in the attempt's out/, not assets"
            )
        slug = asset_slug(
            title, self._run_name(origin.run_id) if isinstance(origin, ExecutionOrigin) else None
        )
        content = _digest_local(path)
        with self._lock():
            occupant = self._slot_occupant(title, origin)
            existing = asset_by_digest(self.workspace, content.digest)
            if existing is not None:
                if occupant is not None and occupant.id != existing.id:
                    self.remove(occupant.id)
                if (
                    occupant is not None
                    and occupant.id == existing.id
                    and existing.origin != origin
                ):
                    # Same bytes from a later attempt: the slot's producer is now that attempt.
                    return self._restamp(existing, origin=origin, created_by=created_by)
                return existing
            if occupant is None and self.fs.exists(self.fs.join(self.assets_dir, slug)):
                raise ValueError(
                    f"asset slug {slug!r} in {self.scope.urn} belongs to another asset; "
                    "give this one a distinct title"
                )
            if occupant is not None:
                self.remove(occupant.id)
            return self._write_new(
                path,
                slug=slug,
                asset_id=occupant.id if occupant is not None else generate_uuid7(),
                content=content,
                title=title,
                created_by=created_by,
                origin=origin,
                media_type=media_type,
                tags=tags or {},
            )

    def slot_slug(self, asset: Asset) -> str:
        """The directory *asset* belongs in: its run's slot for a product, its title otherwise."""
        if isinstance(asset.origin, ExecutionOrigin):
            return asset_slug(asset.title, self._run_name(asset.origin.run_id))
        return asset_slug(asset.title)

    def _run_name(self, run_id: str) -> str:
        """Directory name of run *run_id* under this scope.

        Raises:
            ValueError: No run directory under this scope records *run_id*.
        """
        from molab import frontmatter

        from .entity_record import ENTITY_FILENAME
        from .naming import RUN_CONTAINER

        runs = self.fs.join(self.scope_dir, RUN_CONTAINER)
        if self.fs.exists(runs):
            for name in sorted(self.fs.ls(runs, A=True)):
                head = frontmatter.read_head(self.fs, self.fs.join(runs, name, ENTITY_FILENAME))
                if head and head.get("id") == run_id:
                    return name
        raise ValueError(f"no run under {self.scope.urn} records id {run_id!r}")

    def _restamp(self, asset: Asset, *, origin: AssetOrigin, created_by: AgentRef) -> Asset:
        slug = self.find_slug(asset.id)
        assert slug is not None
        updated = asset.model_copy(
            update={"origin": origin, "created_by": created_by, "created_at": datetime.now(UTC)}
        )
        self.fs.atomic_write_json(
            self.fs.join(self.assets_dir, slug, "asset.json"),
            versioned_payload(updated.model_dump(mode="json")),
        )
        return updated

    def _slot_occupant(self, title: str, origin: AssetOrigin) -> Asset | None:
        for asset in self.list():
            if asset.title != title:
                continue
            if isinstance(origin, ExecutionOrigin):
                if (
                    isinstance(asset.origin, ExecutionOrigin)
                    and asset.origin.run_id == origin.run_id
                ):
                    return asset
            elif isinstance(asset.origin, ImportOrigin):
                return asset
        return None

    def remove(self, asset_id: str) -> str | None:
        """Delete asset *asset_id*'s directory and return its path; a missing id is a no-op.

        Returns:
            The removed slot directory (for the caller's history commit), or
            ``None`` when this scope holds no asset *asset_id*.
        """
        slug = self.find_slug(asset_id)
        if slug is None:
            return None
        directory = self.fs.join(self.assets_dir, slug)
        self.fs.rm(directory, recursive=True)
        return directory

    def list(self) -> builtins.list[Asset]:
        if not self.fs.exists(self.assets_dir):
            return []
        found: list[Asset] = []
        for path in sorted(self.fs.glob(self.assets_dir, "*/asset.json")):
            found.append(self._read_asset(self.fs.dirname(path)))
        return found

    def migrate_legacy(self) -> builtins.list[Asset]:
        """Rewrite versioned asset records into the current schema.

        Keeps the asset id and the payload bytes. Removes ``versions/`` only
        after the current record is on disk and the payload digest matches
        the legacy version. A record that already loads is left as it is.

        Raises:
            UnmigratedAssetError: The legacy version has no recoverable origin.
            ValueError: The payload is missing or its digest does not match.
            RuntimeError: The workspace filesystem is not a local disk.
        """
        if not self.fs.exists(self.assets_dir):
            return []
        migrated: list[Asset] = []
        for path in sorted(self.fs.glob(self.assets_dir, "*/asset.json")):
            directory = self.fs.dirname(path)
            try:
                self._read_asset(directory)
            except UnmigratedAssetError:
                migrated.append(self._migrate_one(directory))
        return migrated

    def get(self, asset_id: str) -> Asset:
        slug = self.find_slug(asset_id)
        if slug is None:
            raise KeyError(f"Asset {asset_id!r} not found in scope {self.scope.urn!r}")
        return self._read_asset(self.fs.join(self.assets_dir, slug))

    def import_asset(
        self,
        title: str,
        source: str | Path,
        *,
        created_by: AgentRef | None = None,
        media_type: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Asset:
        """Register bytes brought in from outside a run.

        The same bytes, registered again anywhere in the workspace, return the
        existing asset. The same title with new bytes replaces that slot and
        keeps its id.
        """
        from .history import SYSTEM_AGENT

        return self.register(
            source,
            title=title,
            created_by=created_by or SYSTEM_AGENT,
            origin=ImportOrigin(uri=str(source)),
            media_type=media_type,
            tags=tags,
        )

    def replace_bytes(
        self,
        asset_id: str,
        source: str | Path,
        *,
        media_type: str | None = None,
    ) -> Asset:
        """Put *source* into asset *asset_id*. The id, title, origin, and tags stay.

        The same bytes are a no-op. A log is refused. Bytes that already belong
        to a different asset are refused: one digest is one asset.

        Raises:
            KeyError: *asset_id* is not in this scope.
            FileNotFoundError: *source* does not exist.
            ValueError: *source* is a log, or another asset already stores its digest.
        """
        import mimetypes

        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")
        if path.is_file() and path.suffix.lower() in _EVIDENCE_SUFFIXES:
            raise ValueError(
                f"{path.name} is a log: logs are evidence and stay in the attempt's out/, not assets"
            )
        content = _digest_local(path)
        with self._lock():
            asset = self.get(asset_id)
            if content.digest == asset.content.digest:
                return asset
            other = asset_by_digest(self.workspace, content.digest)
            if other is not None and other.id != asset.id:
                raise ValueError(
                    f"these bytes are already {other.ref} ({other.title}); "
                    "cite that asset instead of copying them into this one"
                )
            slug = self.find_slug(asset_id)
            assert slug is not None
            asset_root = self.fs.join(self.assets_dir, slug)
            filename = f"payload{path.suffix}" if path.is_file() else "payload"
            guessed = media_type
            if guessed is None and path.is_file():
                guessed = mimetypes.guess_type(path.name)[0]
            updated = asset.model_copy(
                update={
                    "content": content,
                    "file": filename,
                    "media_type": guessed if guessed is not None else asset.media_type,
                }
            )
            staging = self.fs.join(self.root, MOLAB_DIR, "asset-replacements", generate_uuid7())
            prepared = self.fs.join(staging, "new")
            backup = self.fs.join(staging, "previous")
            restore_required = False
            try:
                self.fs.mkdir(prepared, parents=True, exist_ok=False)
                dest = self.fs.join(prepared, filename)
                self._copy_payload(path, dest)
                stored = content_ref(self.fs, dest)
                if stored != content:
                    raise ValueError(
                        f"copied bytes are {stored.digest}, source is {content.digest}"
                    )
                self.fs.atomic_write_json(
                    self.fs.join(prepared, "asset.json"),
                    versioned_payload(updated.model_dump(mode="json")),
                )
                # Switch the complete slot, not the payload and record separately.
                # Keep the old slot until the new one has been installed.
                self.fs.mv(asset_root, backup)
                restore_required = True
                self.fs.mv(prepared, asset_root)
                restore_required = False
            except BaseException:
                if restore_required:
                    self.fs.mv(backup, asset_root)
                    restore_required = False
                raise
            finally:
                # If restoration itself failed, preserve the backup for recovery.
                if not restore_required:
                    with contextlib.suppress(OSError):
                        self.fs.rm(staging, recursive=True)
            return updated

    def _copy_payload(self, source: Path, dest: str) -> None:
        if source.is_dir():
            if isinstance(self.fs, LocalFS):
                shutil.copytree(source, dest)
            else:
                self.fs.cp(str(source), dest, recursive=True)
            return
        if isinstance(self.fs, LocalFS):
            shutil.copy2(source, dest)
            return
        self.fs.cp(str(source), dest)

    def payload_path(self, asset_id: str) -> str:
        """Path of the asset's bytes on the workspace filesystem.

        Raises:
            KeyError: *asset_id* is not in this scope.
            ValueError: The bytes are missing or no longer match the digest.
        """
        asset = self.get(asset_id)
        slug = self.find_slug(asset_id)
        assert slug is not None
        path = self.fs.join(self.assets_dir, slug, asset.file)
        if not self.fs.exists(path):
            raise ValueError(f"asset {asset_id} bytes are missing at {path}")
        current = content_ref(self.fs, path)
        if current.digest != asset.content.digest:
            raise ValueError(
                f"asset {asset_id} bytes are {current.digest}, record has {asset.content.digest}"
            )
        return path

    def _write_new(
        self,
        source: Path,
        *,
        slug: str,
        asset_id: str,
        content: ContentRef,
        title: str,
        created_by: AgentRef,
        origin: AssetOrigin,
        media_type: str | None,
        tags: dict[str, str],
    ) -> Asset:
        import mimetypes

        asset_root = self.fs.join(self.assets_dir, slug)
        filename = f"payload{source.suffix}" if source.is_file() else "payload"
        payload = self.fs.join(asset_root, filename)
        self.fs.mkdir(asset_root, parents=True, exist_ok=True)
        self._copy_payload(source, payload)
        guessed = media_type or (mimetypes.guess_type(source.name)[0] if source.is_file() else None)
        asset = Asset(
            id=asset_id,
            scope=self.scope,
            title=title,
            content=content,
            media_type=guessed,
            origin=origin,
            file=filename,
            created_at=datetime.now(UTC),
            created_by=created_by,
            tags=tags,
        )
        self.fs.atomic_write_json(
            self.fs.join(asset_root, "asset.json"),
            versioned_payload(asset.model_dump(mode="json")),
        )
        return asset

    def _lock(self) -> AbstractContextManager[None]:
        self.fs.mkdir(self.scope_dir, parents=True, exist_ok=True)
        locks = Path(self.root) / ".molab" / "locks"
        locks.mkdir(parents=True, exist_ok=True)
        return file_lock(locks / f"{self.scope.scope_id}.assets.lock")

    def _migrate_one(self, directory: str) -> Asset:
        if not isinstance(self.fs, LocalFS):
            raise RuntimeError("legacy asset migration is local-disk only")
        record_path = self.fs.join(directory, "asset.json")
        stub = json.loads(self.fs.read_text(record_path))
        versions = Path(directory) / "versions"
        legacy = stub
        if versions.is_dir():
            version_files = sorted(versions.glob("v*.json"))
            if not version_files:
                raise UnmigratedAssetError(
                    record_path,
                    "versions/ has no vNNN.json to migrate",
                    workspace_root=self.root,
                )
            legacy = json.loads(version_files[-1].read_text(encoding="utf-8"))
        origin_raw = legacy.get("origin")
        if not isinstance(origin_raw, dict):
            raise UnmigratedAssetError(
                record_path,
                "legacy record has no origin",
                workspace_root=self.root,
            )
        origin = _legacy_origin(origin_raw)
        content_raw = legacy.get("content")
        if not isinstance(content_raw, dict):
            raise UnmigratedAssetError(
                record_path,
                "legacy record has no content",
                workspace_root=self.root,
            )
        payloads = [
            path
            for path in Path(directory).iterdir()
            if path.name not in {"asset.json", "versions"} and not path.name.startswith(".")
        ]
        if len(payloads) != 1:
            names = ", ".join(path.name for path in payloads) or "(none)"
            raise ValueError(f"asset {directory} needs one payload file, found {names}")
        payload = payloads[0]
        content = content_ref(self.fs, str(payload))
        recorded = ContentRef.model_validate(content_raw)
        if content.digest != recorded.digest or content.size != recorded.size:
            raise ValueError(
                f"asset {directory} payload is {content.digest} ({content.size} bytes), "
                f"legacy record has {recorded.digest} ({recorded.size} bytes)"
            )
        created_by = AgentRef.model_validate(stub.get("created_by") or legacy.get("created_by"))
        asset = Asset(
            id=str(stub.get("id") or legacy.get("asset_id")),
            scope=self.scope,
            title=str(stub.get("title") or legacy.get("title") or payload.stem),
            content=content,
            media_type=legacy.get("media_type") or stub.get("media_type"),
            origin=origin,
            file=payload.name,
            created_at=stub.get("created_at") or legacy.get("created_at"),
            created_by=created_by,
            tags=dict(stub.get("tags") or {}),
        )
        self.fs.atomic_write_json(record_path, versioned_payload(asset.model_dump(mode="json")))
        if versions.is_dir():
            shutil.rmtree(versions)
        return self._read_asset(directory)

    def _read_asset(self, directory: str) -> Asset:
        path = self.fs.join(directory, "asset.json")
        raw = json.loads(self.fs.read_text(path))
        raw.pop("schema_version", None)
        if self.fs.exists(self.fs.join(directory, "versions")) or "origin" not in raw:
            raise UnmigratedAssetError(
                path,
                "versioned asset record",
                workspace_root=self.root,
            )
        return Asset.model_validate({**raw, "scope": self.scope})

    def _slugs(self) -> set[str]:
        if not self.fs.exists(self.assets_dir):
            return set()
        return {
            name
            for name in self.fs.ls(self.assets_dir, A=True)
            if self.fs.is_dir(self.fs.join(self.assets_dir, name))
        }

    def find_slug(self, asset_id: str) -> str | None:
        for slug in sorted(self._slugs()):
            path = self.fs.join(self.assets_dir, slug, "asset.json")
            if not self.fs.exists(path):
                continue
            directory = self.fs.join(self.assets_dir, slug)
            if self.fs.exists(self.fs.join(directory, "versions")):
                raise UnmigratedAssetError(
                    path,
                    "versioned asset record",
                    workspace_root=self.root,
                )
            raw = json.loads(self.fs.read_text(path))
            if raw.get("id") == asset_id:
                return slug
        return None


__all__ = [
    "AssetRepository",
    "asset_by_digest",
    "asset_by_id",
    "asset_slug",
    "assets_produced_by",
    "content_ref",
    "payload_path_for",
    "run_slot_prefix",
    "scan_asset_repositories",
]
