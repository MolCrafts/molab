"""Publish selected registered files and read them as the recipient's UID."""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import threading
import urllib.parse
from collections.abc import Generator
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from mollog import get_logger

from molab.atomicio import atomic_write_json
from molab.fs.local import LocalFS
from molab.workspace.asset_repository import asset_by_id, scan_asset_repositories

from .models import (
    AssetInventoryItem,
    AssetShare,
    AssetShareRequest,
    AssetTransfer,
    PrepareAssetShare,
)
from .permissions import FilesystemPermissionBackend
from .publisher import Publisher
from .settings import read_private_config
from .store import SharingError

logger = get_logger(__name__)


@contextlib.contextmanager
def _open_beneath(root: Path, parts: tuple[str, ...], *, directory: bool = False) -> Generator[int]:
    """Open every path component relative to a pinned fd, rejecting symlinks.

    The kernel checks access using the current real process identity. Never
    resolve a string and subsequently reopen it as a privileged service.
    """
    components = (*root.parts[1:], *parts)
    if not root.is_absolute() or any(part in {"", ".", ".."} or "/" in part for part in components):
        raise SharingError(422, "Invalid publication path")
    path_access = getattr(os, "O_PATH", os.O_RDONLY)
    current = os.open("/", path_access | os.O_DIRECTORY)
    try:
        for index, part in enumerate(components):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory or index < len(components) - 1:
                flags = path_access | os.O_NOFOLLOW | os.O_DIRECTORY
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        yield current
    finally:
        os.close(current)


class AssetPublisher:
    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher
        self.storage = publisher.settings.asset_storage
        self._lock = threading.Lock()
        if self.storage is not None:
            if not hasattr(os, "O_PATH"):
                raise ValueError("asset sharing requires Linux O_PATH directory descriptors")
            self.storage_id = hashlib.sha256(str(self.storage.root).encode()).hexdigest()
            source_id = str(
                UUID(publisher.settings.source_token.get_secret_value().partition(".")[0])
            )
            self.pending_root = publisher.approvals / "asset-cleanup" / source_id
            # Mount provisioning belongs to the administrator. Never create or
            # relax permissions on arbitrary ancestors to make sharing work.
            with _open_beneath(self.storage.root, (), directory=True) as fd:
                info = os.fstat(fd)
                if info.st_uid != 0 and info.st_uid != os.getuid():
                    raise ValueError("publication root must be owned by root or this UID")
                if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
                    raise ValueError("writable publication root requires the sticky bit")
            for parent in self.storage.root.parents:
                ancestor = parent.stat()
                if ancestor.st_uid not in {0, os.getuid()} or (
                    ancestor.st_mode & 0o022 and not ancestor.st_mode & stat.S_ISVTX
                ):
                    raise ValueError(
                        "publication root ancestors must prevent replacement by another UID"
                    )
            self.owner_root = self.storage.root / str(publisher.settings.uid)
            try:
                self.owner_root.mkdir(mode=0o711)
                # Set the mode only on the directory we just created, so a
                # private umask does not prevent recipient traversal.
                self.owner_root.chmod(0o711)
            except FileExistsError:
                pass
            with _open_beneath(self.owner_root, (), directory=True) as fd:
                info = os.fstat(fd)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o711:
                    raise ValueError(
                        "owner publication directory must belong to this UID with mode 0711"
                    )

    def inventory(self, project_id: str) -> list[AssetInventoryItem]:
        self.publisher.workspace.get_project(project_id)
        return [
            AssetInventoryItem(
                id=asset.id,
                title=asset.title,
                digest=asset.content.digest,
                size=asset.content.size,
                kind=asset.content.kind,
            )
            for repository in scan_asset_repositories(self.publisher.workspace)
            for asset in repository.list()
            if asset.project_id == project_id
        ]

    def publish(self, body: AssetShareRequest) -> AssetShare:
        if self.storage is None:
            raise SharingError(422, "Asset sharing has not been configured for this cluster")
        workspace = self.publisher.workspace
        if not isinstance(workspace.fs, LocalFS):
            raise SharingError(422, "Asset sharing requires the cluster-local workspace filesystem")
        with self._lock:
            self.publisher.verify_source()
            asset = asset_by_id(workspace, body.asset_id)
            if asset is None or asset.project_id != body.project_id:
                raise SharingError(404, "Asset not found in this project")
            if asset.content.kind != "file":
                raise SharingError(
                    422, "Directory assets must be packaged as a registered archive before sharing"
                )
            if asset.content.digest != body.digest:
                raise SharingError(
                    409, "Asset bytes changed; review the new digest before publishing"
                )
            if asset.content.size > self.storage.max_file_bytes:
                raise SharingError(413, "Asset exceeds the cluster's publication size limit")
            repository = workspace.assets_at(asset.scope)
            slug = repository.find_slug(asset.id)
            if slug is None:
                raise SharingError(404, "Asset no longer exists")
            # Asset.file is persisted user data: it must not select a path.
            if Path(asset.file).name != asset.file or asset.file in {".", "..", ""}:
                raise SharingError(422, "Asset payload must name one regular file")
            source = Path(repository.assets_dir) / slug / asset.file
            preparation = PrepareAssetShare(
                workspace_id=workspace.metadata.id,
                project_id=body.project_id,
                asset_id=asset.id,
                recipient_id=body.recipient_id,
                title=asset.title,
                digest=body.digest,
                size=asset.content.size,
                storage_id=self.storage_id,
            )
            transfer = AssetTransfer.model_validate(
                self.publisher.request(
                    "POST", "/internal/sharing/assets", preparation.model_dump(mode="json")
                )
            )
            self._check_transfer(transfer, owner=True)
            directory = self.owner_root / transfer.id
            pending_path = self.pending_root / f"{transfer.id}.json"
            try:
                # A durable cleanup intent closes the crash/uncertain-commit
                # window. An interrupted publication is revoked on restart.
                atomic_write_json(pending_path, transfer.model_dump(mode="json"))
                directory.mkdir(mode=0o700)
                backend = FilesystemPermissionBackend(self.storage, directory)
                backend.prepare(directory)
                payload = directory / "payload"
                # Copy through no-follow descriptors; never hardlink a mutable
                # workspace slot into a published snapshot or preserve xattrs.
                with _open_beneath(source.parent, (source.name,)) as source_fd:
                    before = os.fstat(source_fd)
                    if not stat.S_ISREG(before.st_mode) or before.st_size != asset.content.size:
                        raise SharingError(409, "Asset bytes changed before publication")
                    target_fd = os.open(
                        payload, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    with os.fdopen(target_fd, "wb") as target:
                        digest, size = hashlib.sha256(), 0
                        while chunk := os.read(source_fd, 1024 * 1024):
                            size += len(chunk)
                            if size > asset.content.size:
                                raise SharingError(409, "Asset grew during publication")
                            digest.update(chunk)
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                    after = os.fstat(source_fd)
                    if (
                        (before.st_mtime_ns, before.st_ctime_ns, before.st_size)
                        != (after.st_mtime_ns, after.st_ctime_ns, after.st_size)
                        or size != asset.content.size
                        or "sha256:" + digest.hexdigest() != body.digest
                    ):
                        raise SharingError(409, "Asset bytes changed during publication")
                backend.grant(directory, payload, transfer.recipient_uid)
                # Persist directory entries before exposing an active catalog
                # record. O_PATH descriptors themselves cannot be fsynced.
                for path in (directory, self.owner_root):
                    with _open_beneath(path, (), directory=True) as path_fd:
                        sync_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=path_fd)
                        try:
                            os.fsync(sync_fd)
                        finally:
                            os.close(sync_fd)
                result = AssetShare.model_validate(
                    self.publisher.request("POST", f"/internal/sharing/assets/{transfer.id}/commit")
                )
                pending_path.unlink()
                return result
            except BaseException:
                # Uncertain HTTP commits can leave a live grant. Remove its
                # filesystem entry first; no metadata can make it readable.
                try:
                    self._remove(transfer)
                    self.publisher.request(
                        "POST", f"/internal/sharing/assets/{transfer.id}/removed"
                    )
                    pending_path.unlink(missing_ok=True)
                except (OSError, SharingError):
                    logger.warning("Asset cleanup is pending; the owner service will retry")
                raise

    def _check_transfer(self, transfer: AssetTransfer, *, owner: bool) -> None:
        settings = self.publisher.settings
        # A path locator is an opaque UUID, never a gateway-supplied path.
        try:
            valid_id = str(UUID(transfer.id)) == transfer.id
        except ValueError:
            valid_id = False
        if not valid_id or transfer.cluster_id != settings.cluster_id:
            raise SharingError(502, "Gateway returned an invalid asset locator")
        if self.storage is None or transfer.storage_id != self.storage_id:
            raise SharingError(
                409, "Asset belongs to a different publication storage configuration"
            )
        expected = transfer.owner_uid if owner else transfer.recipient_uid
        if expected != settings.uid:
            raise SharingError(403, "Asset identity does not match this user service")
        if not owner and transfer.recipient_id != settings.principal_id:
            raise SharingError(403, "Asset recipient does not match this user service")

    def _remove(self, transfer: AssetTransfer) -> None:
        self._check_transfer(transfer, owner=True)
        with _open_beneath(self.owner_root, (), directory=True) as path_fd:
            parent_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY, dir_fd=path_fd)
            try:
                try:
                    directory_fd = os.open(
                        transfer.id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
                    )
                except FileNotFoundError:
                    os.fsync(parent_fd)
                    return
                try:
                    # Persist physical removal before acknowledging revocation.
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink("payload", dir_fd=directory_fd)
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                os.rmdir(transfer.id, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)

    def reconcile(self) -> None:
        if self.storage is None:
            return
        with self._lock:
            for path in sorted(self.pending_root.glob("*.json")):
                try:
                    transfer = AssetTransfer.model_validate_json(read_private_config(path))
                    self._remove(transfer)
                    self.publisher.request(
                        "POST", f"/internal/sharing/assets/{transfer.id}/removed"
                    )
                    path.unlink()
                except (OSError, ValueError, SharingError):
                    logger.warning("An interrupted asset publication still awaits cleanup")
            after_id = ""
            while True:
                query = urllib.parse.urlencode({"after_id": after_id})
                pending = self.publisher.request("GET", "/internal/sharing/assets/cleanup?" + query)
                rows = pending.get("items")
                if not isinstance(rows, list) or len(rows) > 100:
                    raise SharingError(502, "Gateway returned an invalid cleanup batch")
                if not rows:
                    break
                for raw in rows:
                    transfer = AssetTransfer.model_validate(raw)
                    if transfer.id <= after_id:
                        raise SharingError(502, "Gateway returned an invalid cleanup cursor")
                    after_id = transfer.id
                    try:
                        self._remove(transfer)
                        self.publisher.request(
                            "POST", f"/internal/sharing/assets/{transfer.id}/removed"
                        )
                    except (OSError, SharingError):
                        logger.warning("A shared file still awaits filesystem revocation")

    def open_download(self, asset_share_id: str) -> tuple[AssetTransfer, BinaryIO]:
        if self.storage is None:
            raise SharingError(422, "Asset storage is unavailable on this user service")
        try:
            if str(UUID(asset_share_id)) != asset_share_id:
                raise ValueError("noncanonical share id")
        except ValueError as exc:
            raise SharingError(404, "Asset share not found") from exc
        transfer = AssetTransfer.model_validate(
            self.publisher.request("GET", f"/internal/sharing/assets/{asset_share_id}/access")
        )
        self._check_transfer(transfer, owner=False)
        try:
            with _open_beneath(
                self.storage.root, (str(transfer.owner_uid), transfer.id, "payload")
            ) as fd:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != transfer.owner_uid
                    or info.st_size != transfer.size
                ):
                    raise SharingError(
                        409, "Published asset no longer matches its recorded snapshot"
                    )
                handle = os.fdopen(os.dup(fd), "rb")
            return transfer, handle
        except OSError as exc:
            raise SharingError(
                403, "Linux permissions do not allow this UID to read the published asset"
            ) from exc
