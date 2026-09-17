"""Per-scope asset manifest — ``assets.json`` in each scope directory.

Layout::

    {
      "schema_version": 1,
      "assets": {
        "<asset_id>": { ...Asset serialization... },
        ...
      }
    }

Writes go through a process-local lock + atomic rename so concurrent
tasks inside a single run process can append assets safely.  Cross-process
coordination is out of scope (see spec §2).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

from ._adapter import ASSET_ADAPTER, parse_asset
from .base import Asset

if TYPE_CHECKING:
    from ..fs import FileSystem

SCHEMA_VERSION = 1
MANIFEST_FILENAME = "assets.json"

# Alias avoids the static-checker confusion where ``list`` (the method) shadows
# ``list`` (the builtin) in return annotations.
type AssetList = list[Asset]


class AssetManifest:
    """JSON-backed dict of assets for one scope.

    ``scope_dir`` is the scope directory. I/O goes through *fs*
    (``workspace.fs``); the default is the local filesystem.
    """

    def __init__(
        self,
        scope_dir: str | PathLike[str],
        *,
        fs: FileSystem | None = None,
    ) -> None:
        from ..fs_local import LocalFileSystem

        self._fs = fs or LocalFileSystem()
        self.scope_dir = Path(os.fspath(scope_dir))
        self.path = Path(self._fs.join(os.fspath(scope_dir), MANIFEST_FILENAME))
        self._lock = threading.Lock()

    # ── Read ──────────────────────────────────────────────────────────────

    def load(self) -> dict[str, Asset]:
        """Return a fresh mapping ``{asset_id -> Asset}`` from disk."""
        if not self._fs.exists(str(self.path)):
            return {}
        with self._fs.open(str(self.path)) as fh:
            data = json.load(fh)
        raw_assets: dict = data.get("assets", {})
        return {aid: parse_asset(entry) for aid, entry in raw_assets.items()}

    def get(self, asset_id: str) -> Asset | None:
        return self.load().get(asset_id)

    def list(self) -> AssetList:
        return list(self.load().values())

    def __iter__(self) -> Iterator[Asset]:
        return iter(self.list())

    # ── Write ─────────────────────────────────────────────────────────────

    def register(self, asset: Asset) -> None:
        """Insert ``asset`` into the manifest (overwrites if asset_id exists)."""
        with self._lock:
            assets = self._load_raw()
            assets[asset.asset_id] = _dump(asset)
            self._save_raw(assets)

    def update(self, asset: Asset) -> None:
        """Replace an existing entry.  Raises ``KeyError`` if missing."""
        with self._lock:
            assets = self._load_raw()
            if asset.asset_id not in assets:
                raise KeyError(f"Asset {asset.asset_id!r} not in manifest at {self.path}")
            assets[asset.asset_id] = _dump(asset)
            self._save_raw(assets)

    def deregister(self, asset_id: str) -> None:
        with self._lock:
            assets = self._load_raw()
            assets.pop(asset_id, None)
            self._save_raw(assets)

    # ── Internal ──────────────────────────────────────────────────────────

    def _load_raw(self) -> dict:
        if not self._fs.exists(str(self.path)):
            return {}
        with self._fs.open(str(self.path)) as fh:
            data = json.load(fh)
        return dict(data.get("assets", {}))

    def _save_raw(self, assets: dict) -> None:
        payload = {"schema_version": SCHEMA_VERSION, "assets": assets}
        self._fs.atomic_write_json(str(self.path), payload)


def _dump(asset: Asset) -> dict:
    return ASSET_ADAPTER.dump_python(asset, mode="json")
