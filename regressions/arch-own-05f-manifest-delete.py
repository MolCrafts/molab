"""arch-own-05f-manifest-delete: unified assets, public API only."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import molab.ids
import molab.workflow.protocols
import molab.workspace
import molab.workspace.assets
import molab.workspace.domain
from molab.workspace import Workspace
from molab.workspace.errors import UnmigratedAssetError

HELLO = b"hello\n"
LEGACY = b"legacy\n"
DIGEST = "sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
LEGACY_ID = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6b"
CREATED = "2026-01-01T00:00:00Z"
_DELETED = (
    "manifest",
    "scan",
    "view",
    "accessors",
    "data",
    "artifact",
    "log",
    "checkpoint",
    "error",
    "_adapter",
    "base",
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab"
        ws = Workspace(root=root, name="Lab")
        ws.materialize()
        source = Path(tmp) / "greeting.txt"
        source.write_bytes(HELLO)
        asset = ws.data_assets.import_asset("greeting", source)
        assert molab.workspace.Asset is molab.workspace.domain.Asset
        assert type(asset) is molab.workspace.Asset
        version = ws.assets.versions(asset.id)[0]
        assert version.origin.kind == "import"
        assert version.origin.action == "copy"
        assert version.content is not None
        assert version.content.digest == DIGEST
        assert version.content.size == 6
        assert Path(ws.assets.payload_path(asset.id)).read_bytes() == HELLO

        record = root / "assets" / LEGACY_ID
        record.mkdir(parents=True)
        (record / "asset.json").write_text(
            json.dumps(
                {
                    "kind": "data",
                    "asset_id": LEGACY_ID,
                    "name": "legacy-data",
                    "scope": {"kind": "workspace", "ids": []},
                    "path": f"assets/{LEGACY_ID}/payload",
                    "created_at": CREATED,
                    "updated_at": CREATED,
                    "producer": None,
                    "tags": {},
                    "content_hash": None,
                    "external_uri": None,
                    "source_path": "/data/legacy.bin",
                    "import_action": "copy",
                }
            ),
            encoding="utf-8",
        )
        (record / "payload").write_bytes(LEGACY)
        try:
            ws.assets.list()
        except UnmigratedAssetError as exc:
            assert "molab migrate assets" in str(exc)
        else:
            raise AssertionError("list() accepted a legacy record")

        report = ws.assets.rewrite_legacy()
        assert len(report.rewritten) == 1
        assert report.rewritten[0].endswith(LEGACY_ID)
        assert report.unresolved == ()
        assert sorted(item.title for item in ws.assets.list()) == ["greeting", "legacy-data"]
        assert ws.assets.versions(LEGACY_ID)[0].id == f"{LEGACY_ID}-v001"
        assert Path(ws.assets.payload_path(LEGACY_ID)).read_bytes() == LEGACY
        assert ws.assets.rewrite_legacy().rewritten == ()

        for module in _DELETED:
            assert importlib.util.find_spec(f"molab.workspace.assets.{module}") is None
        assert molab.workspace.assets.__all__ == ["lineage"]
        for name in (
            "DataAssetLibrary",
            "DataAsset",
            "AssetManifest",
            "AssetsView",
            "ArtifactAsset",
            "Producer",
        ):
            assert not hasattr(molab.workspace, name)
        assert not hasattr(molab.workflow.protocols, "AssetsViewLike")
        assert "assets" not in molab.workflow.protocols.UpstreamViewLike.__annotations__
        assert not hasattr(molab.ids, "generate_asset_id")
    print("arch-own-05f-manifest-delete: ok")


if __name__ == "__main__":
    main()
