"""Unit tests for ``molab.workspace.asset_repository``.

One registered file is one asset: one id, one content, one ``molab:asset/<id>``
ref. The same digest anywhere in the workspace returns the existing asset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.asset_repository import (
    AssetRepository,
    asset_by_id,
    assets_produced_by,
    content_ref,
    payload_path_for,
    scan_asset_repositories,
)
from molab.workspace.domain import ExecutionMode, ExecutionOrigin, ImportOrigin
from molab.workspace.errors import UnmigratedAssetError
from molab.workspace.history import AgentRef

_ACTOR = AgentRef(id="t", type="system")


def _ws(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "ws", name="lab")


def _src(tmp_path: Path, name: str = "hello.txt", data: bytes = b"hello\n") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


class TestRegister:
    def test_copies_bytes_and_returns_one_asset(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"seed": 1})
        project = experiment
        src = _src(tmp_path, data=b"abc")
        origin = ExecutionOrigin(
            project_id=experiment.project.id,
            experiment_id=experiment.id,
            run_id=run.id,
            execution_id="e01",
            task="train",
        )
        asset = project.assets.register(
            src, title="note", created_by=_ACTOR, origin=origin, media_type="text/plain"
        )
        assert asset.title == "note"
        assert asset.ref == f"molab:asset/{asset.id}"
        assert asset.origin == origin
        assert asset.file == "payload.txt"
        assert asset.media_type == "text/plain"
        assert Path(project.assets.payload_path(asset.id)).read_bytes() == b"abc"
        assert content_ref(ws.fs, project.assets.payload_path(asset.id)) == asset.content
        assert src.read_bytes() == b"abc"

    def test_a_product_of_an_unknown_run_is_refused(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        origin = ExecutionOrigin(
            project_id=experiment.project.id,
            experiment_id=experiment.id,
            run_id="not-a-run",
            execution_id="e01",
            task="train",
        )
        with pytest.raises(ValueError, match="no run"):
            experiment.assets.register(
                _src(tmp_path), title="note", created_by=_ACTOR, origin=origin
            )

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        with pytest.raises(FileNotFoundError):
            ws.assets.import_asset("gone", tmp_path / "missing.txt")

    def test_same_digest_anywhere_returns_the_existing_asset(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path)
        first = ws.assets.import_asset("root", src)
        project = ws.add_project("p")
        again = project.assets.import_asset("other", src)
        assert again.id == first.id
        assert again.scope.kind == "workspace"
        assert len(list(Path(ws.root).rglob("asset.json"))) == 1

    def test_different_bytes_are_a_new_id(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        first = project.import_asset("a", _src(tmp_path, "a.txt", b"a"))
        second = project.import_asset("b", _src(tmp_path, "b.txt", b"b"))
        assert first.id != second.id
        assert {item.id for item in project.assets.list()} == {first.id, second.id}

    def test_directory_is_one_asset(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        folder = tmp_path / "bundle"
        folder.mkdir()
        (folder / "a.txt").write_text("a", encoding="utf-8")
        asset = project.assets.import_asset("bundle", folder)
        assert asset.content.kind == "directory"
        assert asset.file == "payload"
        payload = Path(project.assets.payload_path(asset.id))
        assert (payload / "a.txt").read_text(encoding="utf-8") == "a"


class TestImportAsset:
    def test_origin_is_the_source_uri(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path, "structures.pdf", b"%PDF-1.4")
        asset = ws.add_project("p").assets.import_asset("Structures", src)
        assert isinstance(asset.origin, ImportOrigin)
        assert asset.origin.uri == str(src)
        assert asset.media_type == "application/pdf"
        assert asset.file == "payload.pdf"
        assert asset.title == "Structures"


class TestPayloadPath:
    def test_round_trip(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path, data=b"abc")
        asset = ws.assets.import_asset("greeting", src)
        assert Path(payload_path_for(ws, asset.id)).read_bytes() == b"abc"
        assert asset_by_id(ws, asset.id) == asset

    def test_missing_bytes_raise(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        Path(ws.assets.payload_path(asset.id)).unlink()
        with pytest.raises(ValueError, match="missing"):
            ws.assets.payload_path(asset.id)

    def test_tampered_bytes_raise(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        Path(ws.assets.payload_path(asset.id)).write_bytes(b"nope")
        with pytest.raises(ValueError, match="bytes are"):
            ws.assets.payload_path(asset.id)

    def test_unknown_id_raises(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        with pytest.raises(KeyError):
            ws.assets.payload_path("missing")
        with pytest.raises(KeyError):
            payload_path_for(ws, "missing")
        assert asset_by_id(ws, "missing") is None


class TestProducedBy:
    def test_only_that_attempt(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            made = ctx.register(b"abc", title="a.bin")
            execution_id = ctx.id
        other = _src(tmp_path, "other.txt", b"zzz")
        imported = experiment.assets.import_asset("other", other)
        assert [asset.id for asset in assets_produced_by(ws, execution_id)] == [made.id]
        assert imported.id not in {asset.id for asset in assets_produced_by(ws, execution_id)}

    def test_a_second_attempt_with_the_same_bytes_produces_nothing(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            made = ctx.register(b"abc", title="a.bin")
            first_id = ctx.id
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            again = ctx.register(b"abc", title="again")
            execution_id = ctx.id
        assert again.id == made.id
        assert execution_id != first_id
        assert assets_produced_by(ws, execution_id) == []
        assert [asset.id for asset in assets_produced_by(ws, first_id)] == [made.id]


class TestScan:
    def test_hosts_are_workspace_project_and_experiment(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        experiment.add_run()
        kinds = [repo.scope.kind for repo in scan_asset_repositories(ws)]
        assert kinds[0] == "workspace"
        assert "project" in kinds
        assert "experiment" in kinds
        assert "run" not in kinds
        assert all(isinstance(repo, AssetRepository) for repo in scan_asset_repositories(ws))


class TestUnmigrated:
    def test_versions_directory_blocks_the_scope(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        record = Path(ws.assets.payload_path(asset.id)).parent
        (record / "versions").mkdir()
        with pytest.raises(UnmigratedAssetError) as exc_info:
            ws.assets.list()
        assert exc_info.value.reason == "versioned asset record"
        assert exc_info.value.workspace_root == str(ws.root)
        with pytest.raises(UnmigratedAssetError):
            ws.assets.get(asset.id)

    def test_missing_origin_blocks_the_record(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        path = Path(ws.assets.payload_path(asset.id)).parent / "asset.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("origin")
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(UnmigratedAssetError) as exc_info:
            ws.assets.get(asset.id)
        assert exc_info.value.reason == "versioned asset record"

    def test_migrate_legacy_restores_a_versioned_import(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        record = Path(ws.assets.payload_path(asset.id)).parent
        current = json.loads((record / "asset.json").read_text(encoding="utf-8"))
        version = {
            "asset_id": asset.id,
            "content": current["content"],
            "origin": {
                "action": "copy",
                "input_ids": [],
                "kind": "import",
                "location": "assets/greeting/payload.txt",
                "uri": current["origin"]["uri"],
            },
            "media_type": None,
            "version": 1,
        }
        (record / "versions").mkdir()
        (record / "versions" / "v001.json").write_text(json.dumps(version), encoding="utf-8")
        stub = {
            "created_at": current["created_at"],
            "created_by": current["created_by"],
            "id": asset.id,
            "schema_version": 6,
            "tags": current.get("tags", {}),
            "title": current["title"],
        }
        (record / "asset.json").write_text(json.dumps(stub), encoding="utf-8")
        migrated = ws.assets.migrate_legacy()
        assert [item.id for item in migrated] == [asset.id]
        assert not (record / "versions").exists()
        loaded = ws.assets.get(asset.id)
        assert loaded.origin.uri == current["origin"]["uri"]
        assert loaded.content.digest == current["content"]["digest"]
        assert loaded.file == asset.file
        assert ws.assets.migrate_legacy() == []
        assert ws.assets.list()

    def test_schema_version_alone_still_loads(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        path = Path(ws.assets.payload_path(asset.id)).parent / "asset.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["schema_version"] = 1
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert ws.assets.get(asset.id).id == asset.id
