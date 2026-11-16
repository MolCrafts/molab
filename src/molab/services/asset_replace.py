"""Replace the bytes of one registered asset — the path ``molab asset replace`` takes.

The asset is named the same way as delete: its id, its ``molab:asset/<id>``
ref, or its slot directory. The id, title, origin, and tags stay, so a
citation keeps naming this asset. The payload and its digest are rewritten.
The same bytes are a no-op. A change is one ``AssetReplaced`` history commit.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from molab.workspace import Workspace
    from molab.workspace.domain import Asset

__all__ = ["ReplacedAsset", "replace_asset"]


@dataclass(frozen=True)
class ReplacedAsset:
    """What :func:`replace_asset` wrote."""

    asset: Asset
    path: str
    """The slot directory."""
    changed: bool


def replace_asset(
    ws: Workspace,
    spec: str,
    source: str | Path,
    *,
    media_type: str | None = None,
) -> ReplacedAsset:
    """Replace the bytes of the asset *spec* names with *source*.

    Raises:
        RefNotFoundError: No asset matches *spec*.
        AmbiguousRefError: The id exists in more than one scope.
        InvalidRefError: *spec* is a ``molab:`` reference that is not an asset ref.
        FileNotFoundError: *source* does not exist.
        ValueError: *source* is a log, or another asset already stores its digest.
    """
    from molab.services.asset_delete import resolve_asset
    from molab.workspace.history import EntityRef, GitHistory

    asset, repository = resolve_asset(ws, spec)
    previous = asset.content.digest
    updated = repository.replace_bytes(asset.id, source, media_type=media_type)
    slug = repository.find_slug(updated.id)
    if slug is None:
        raise KeyError(updated.id)
    slot = repository.fs.join(repository.assets_dir, slug)
    changed = updated.content.digest != previous
    if changed:
        GitHistory(str(ws.root)).record(
            "AssetReplaced",
            subject=EntityRef(id=updated.id, type="asset"),
            summary=(
                f"{updated.title} "
                f"{posixpath.relpath(posixpath.normpath(slot), posixpath.normpath(str(ws.root)))}"
            ),
            paths=(slot,),
        )
    return ReplacedAsset(asset=updated, path=slot, changed=changed)
