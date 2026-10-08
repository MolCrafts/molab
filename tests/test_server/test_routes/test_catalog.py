"""``GET /api/catalog/by-path`` resolves emitted artifacts by id."""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace


class TestCatalogByPath:
    def test_emitted_artifact_matches(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"hi", name="note.txt")
            location = run.artifact_location(ctx.id, artifact)
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": location})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matched"] is True
        assert body["assetId"] == artifact.id
        assert body["scope"]["experimentId"] == experiment.id
        assert body["producer"]["executionId"] == "e01"

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
        asset = ws.data_assets.import_asset("greeting", src, action="copy")
        payload = ws.assets.payload_path(asset.id)
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": payload})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matched"] is True
        assert body["assetKind"] == "asset"
        assert body["scope"]["kind"] == "workspace"
        assert body["siblings"] == []
        assert body["producer"] is None

    def test_promoted_payload_keeps_the_artifact_producer(self, served, tmp_path: Path) -> None:
        from molab.workspace.history import AgentRef

        ws = Workspace(tmp_path / "ws", name="lab")
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            path = ctx.get_dir("work") / "hello.txt"
            path.write_bytes(b"hello\n")
            artifact = ctx.emit_artifact(path, name="hello.txt")
        asset, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        payload = project.assets.payload_path(asset.id)
        with served(ws) as client:
            response = client.get("/api/catalog/by-path", params={"path": payload})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["assetId"] == asset.id
        assert body["producer"]["runId"] == run.id
        assert body["producer"]["executionId"] == "e01"
