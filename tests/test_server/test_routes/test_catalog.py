"""``GET /api/catalog/by-path`` resolves a registered asset by its payload path."""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace


class TestCatalogByPath:
    def test_registered_asset_matches(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            asset = ctx.register(b"hi", title="note.txt", mime="text/plain")
        location = experiment.assets.payload_path(asset.id)
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": location})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matched"] is True
        assert body["assetId"] == asset.id
        assert body["assetKind"] == "text/plain"
        assert body["scope"]["kind"] == "experiment"
        assert body["scope"]["experimentId"] == experiment.id
        assert body["producer"]["executionId"] == "e01"
        assert body["producer"]["runId"] == run.id

    def test_unregistered_run_file_reports_entity_ids(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start():
            pass
        note = run.execution_dir("e01") / "out" / "plain.txt"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("x", encoding="utf-8")
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": str(note)})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matched"] is False
        assert body["scope"]["runId"] == run.id
        assert body["scope"]["projectId"] == project.id

    def test_outside_path_is_400(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        outside = tmp_path / "outside.txt"
        outside.write_text("no", encoding="utf-8")
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": str(outside)})
        assert response.status_code == 400

    def test_imported_payload_is_a_named_asset(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        src = tmp_path / "hello.txt"
        src.write_bytes(b"hello\n")
        asset = ws.assets.import_asset("greeting", src)
        payload = ws.assets.payload_path(asset.id)
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": payload})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matched"] is True
        assert body["assetKind"] == "text/plain"
        assert body["scope"]["kind"] == "workspace"
        assert body["siblings"] == []
        assert body["producer"] is None

    def test_execution_payload_keeps_the_producer(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            asset = ctx.register(b"hello\n", title="hello.txt")
        payload = experiment.assets.payload_path(asset.id)
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": payload})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["assetId"] == asset.id
        assert body["producer"]["runId"] == run.id
        assert body["producer"]["executionId"] == "e01"
