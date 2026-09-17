"""Scope-bound asset view — ``{scope}.assets``.

Returned by ``Workspace.assets`` / ``Project.assets`` /
``Experiment.assets`` / ``Run.assets``.  Presents the scope as a
read-only filtered view over the authoritative per-scope ``assets.json``
manifests, scanned on demand (see :mod:`molab.workspace.assets.scan`).

For importing ``DataAsset`` inputs, use ``{scope}.data_assets`` instead.
"""

from __future__ import annotations

from os import PathLike
from typing import TYPE_CHECKING

from . import scan
from .base import Asset, AssetScope

if TYPE_CHECKING:
    from ..fs import FileSystem

# Alias avoids the static-checker confusion where the ``list`` method name
# shadows the ``list`` builtin in return-type expressions.
type AssetList = list[Asset]


class AssetsView:
    """Read-only, scope-filtered view over the workspace's asset manifests.

    Every query is answered from this scope's own directory
    (:func:`~molab.workspace.assets.scan.scope_dir_for`) — one manifest for
    an exact-scope query, that subtree for a recursive one — and goes through
    the owning folder's *fs* so a remote-backed workspace scans over its
    transport instead of assuming a local path.
    """

    def __init__(
        self,
        workspace_root: str | PathLike[str],
        scope: AssetScope,
        *,
        fs: FileSystem | None = None,
    ) -> None:
        self._root = workspace_root
        self._scope = scope
        self._fs = fs

    def list(self) -> AssetList:
        return scan.scan_assets(self._root, scope=self._scope, fs=self._fs)

    # Alias that mirrors the old API surface.
    def list_assets(self) -> AssetList:
        return self.list()

    def get(self, asset_id: str) -> Asset | None:
        """The asset with *asset_id* **in this scope**, else ``None``.

        The scope is known, so this reads one manifest rather than walking
        the workspace for an id.
        """
        for asset in scan.scan_assets(self._root, scope=self._scope, fs=self._fs):
            if asset.asset_id == asset_id:
                return asset
        return None

    def query(
        self,
        *,
        kind: str | type[Asset] | None = None,
        producer_run: str | None = None,
        producer_task: str | None = None,
        tag: tuple[str, str] | None = None,
        limit: int | None = None,
        recursive: bool = False,
    ) -> AssetList:
        """Filtered asset query at this scope, scanned from the manifests.

        When ``recursive`` is ``True``, matches assets in any sub-scope
        underneath this view's scope — for instance an
        ``experiment.assets.query(recursive=True)`` returns assets
        produced by every run in the experiment.
        """
        return scan.scan_assets(
            self._root,
            kind=kind,
            scope=self._scope,
            producer_run=producer_run,
            producer_task=producer_task,
            tag=tag,
            limit=limit,
            recursive=recursive,
            fs=self._fs,
        )
