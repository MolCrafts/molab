"""arch-own-05e-asset-writers: import_asset, public API only."""

from __future__ import annotations

import tempfile
from pathlib import Path

import molab.workspace
from molab.workspace import Workspace
from molab.workspace.domain import Asset

HELLO = b"hello\n"
DIGEST = "sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab"
        ws = Workspace(root, name="Lab")
        source = Path(tmp) / "greeting.txt"
        source.write_bytes(HELLO)
        asset = ws.data_assets.import_asset("greeting", source)
        assert type(asset) is Asset
        version = ws.data_assets.versions(asset.id)[0]
        assert version.version == 1
        assert version.origin.action == "copy"
        assert version.origin.location == "assets/greeting/payload"
        assert version.content is not None
        assert version.content.digest == DIGEST
        assert version.content.size == 6
        assert Path(ws.data_assets.payload_path(asset.id)).read_bytes() == HELLO

        remote = ws.data_assets.import_asset("remote", source, action="reference")
        remote_version = ws.data_assets.versions(remote.id)[0]
        assert remote_version.origin.location is None
        assert ws.data_assets.payload_path(remote.id) == str(source.resolve())
        assert not hasattr(molab.workspace, "DataAssetLibrary")
    print("arch-own-05e-asset-writers: ok")


if __name__ == "__main__":
    main()
