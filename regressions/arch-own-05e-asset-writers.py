"""arch-own-05e-asset-writers: import and legacy migration, public API only."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import molab.workspace
from molab.workspace import Workspace
from molab.workspace.artifact_repository import migrate_legacy_assets
from molab.workspace.domain import Asset
from molab.workspace.refs import MolabRef

HELLO = b"hello\n"
DIGEST = "sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
LEGACY_ID = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6b"
MODEL_ID = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6d"
CREATED = "2026-01-02T03:04:05"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab"
        ws = Workspace(root, name="Lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run(params={"seed": 1})
        with run.start() as ctx:
            artifact = ctx.emit_artifact(HELLO, name="hello.txt")

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

        created_by = {"id": "molab", "type": "system", "name": "Molab"}
        legacy_dir = root / "assets" / LEGACY_ID
        _write(
            legacy_dir / "asset.json",
            {
                "kind": "data",
                "asset_id": LEGACY_ID,
                "name": "legacy-data",
                "scope": {"kind": "workspace", "ids": []},
                "path": f"assets/{LEGACY_ID}/payload",
                "created_at": CREATED,
                "updated_at": CREATED,
                "producer": {"inputs": []},
                "tags": {},
                "content_hash": DIGEST,
                "external_uri": None,
                "source_path": "/data/hello.bin",
                "import_action": "copy",
            },
        )
        (legacy_dir / "payload").write_bytes(HELLO)
        _write(
            Path(project.project_dir) / "assets" / "model" / "asset.json",
            {
                "schema_version": 3,
                "id": MODEL_ID,
                "project_id": project.id,
                "title": "model",
                "created_at": CREATED,
                "created_by": created_by,
                "tags": {},
            },
        )
        _write(
            Path(project.project_dir) / "assets" / "model" / "versions" / "v001.json",
            {
                "schema_version": 3,
                "id": f"{MODEL_ID}-v001",
                "asset_id": MODEL_ID,
                "source_artifact_id": artifact.id,
                "path": "projects/p/assets/model/payload",
                "content": {"digest": DIGEST, "size": 6, "kind": "file"},
                "version": 1,
                "created_at": CREATED,
                "created_by": created_by,
            },
        )
        manifest = root / "assets.json"
        _write(manifest, {"schema_version": 1, "assets": {}})

        preview = migrate_legacy_assets(ws, dry_run=True)
        assert len(preview.rewritten) == 2
        assert len(preview.manifests_removed) == 1
        assert manifest.is_file()

        report = migrate_legacy_assets(ws)
        assert len(report.rewritten) == 2
        assert len(report.manifests_removed) == 1
        assert not manifest.exists()
        assert ws.assets.get(LEGACY_ID).title == "legacy-data"
        folded = ws.assets.versions(LEGACY_ID)[0]
        assert folded.id == f"{LEGACY_ID}-v001"
        assert folded.content is not None
        assert folded.content.digest == DIGEST
        assert (legacy_dir / "payload").read_bytes() == HELLO
        assert legacy_dir.is_dir()
        qualified = project.assets.versions(MODEL_ID)[0].origin.ref
        assert qualified == str(
            MolabRef(experiment_id=experiment.id, run_id=run.id, artifact_id=artifact.id)
        )

        again = migrate_legacy_assets(ws)
        assert again.rewritten == ()
        assert again.manifests_removed == ()
        assert not hasattr(molab.workspace, "DataAssetLibrary")
    print("arch-own-05e-asset-writers: ok")


if __name__ == "__main__":
    main()
