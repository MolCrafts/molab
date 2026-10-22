"""``/api/workspace/{context,copilot}`` consume the services knowledge projection."""

from __future__ import annotations

import inspect
from pathlib import Path

from fastapi.testclient import TestClient

from molab.knowledge import Note
from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.server.routes import workspace as workspace_routes
from molab.workspace import Workspace

_IDEA_GOLDEN = {"path": "knowledges/idea.md", "type": "Note", "title": "Idea", "id": "idea"}


def _client(tmp_path: Path, *, with_note: bool = False) -> TestClient:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    if with_note:
        Note(Path(str(ws.root)) / "knowledges" / "idea").write("# Idea\n")
    set_workspace_path_override(Path(str(ws.root)))
    return TestClient(create_app(serve_static=False))


def _workspace_files(ws: Workspace) -> set[str]:
    """Every workspace file, git internals excluded (they are not user writes)."""
    root = Path(str(ws.root))
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git/" not in p.relative_to(root).as_posix()
    }


class TestContextConsumesProjection:
    def test_consumes_services_projection(self) -> None:
        for handler in (
            workspace_routes.get_workspace_context,
            workspace_routes.get_workspace_copilot,
        ):
            src = inspect.getsource(handler)
            assert "context_with_knowledge" in src
            assert "molab.services.knowledge_context" in src
        module_src = inspect.getsource(workspace_routes)
        assert "_knowledge_refs" not in module_src
        assert "model_copy" not in module_src
        assert not hasattr(workspace_routes, "_knowledge_refs")

    def test_context_projects_the_note_file(self, tmp_path: Path) -> None:
        client = _client(tmp_path, with_note=True)
        with client:
            response = client.get("/api/workspace/context")
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {
            "workspace",
            "focus",
            "projects",
            "experiments",
            "workflows",
            "recentRuns",
            "failedRuns",
            "runningRuns",
            "artifacts",
            "knowledge",
            "staleOrMissing",
        }
        assert body["knowledge"] == [_IDEA_GOLDEN]

    def test_copilot_reports_the_same_knowledge(self, tmp_path: Path) -> None:
        client = _client(tmp_path, with_note=True)
        with client:
            response = client.get("/api/workspace/copilot")
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == {
            "workspace",
            "headline",
            "counts",
            "failedRuns",
            "runningRuns",
            "healthFlags",
            "relevantKnowledge",
            "nextActions",
        }
        assert set(body["counts"]) == {
            "projects",
            "experiments",
            "workflows",
            "recent_runs",
            "failed_runs",
            "running_runs",
            "artifacts",
            "knowledge",
            "health_flags",
        }
        assert body["relevantKnowledge"] == [_IDEA_GOLDEN]

    def test_empty_workspace_projects_nothing(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        with client:
            context = client.get("/api/workspace/context")
            copilot = client.get("/api/workspace/copilot")
        set_workspace_path_override(None)
        assert context.status_code == 200, context.text
        assert context.json()["knowledge"] == []
        assert copilot.status_code == 200, copilot.text
        assert copilot.json()["relevantKnowledge"] == []

    def test_focus_writes_nothing(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        exp = ws.add_project("p").add_experiment("e")
        run = exp.add_run(params={"x": 1})
        before = _workspace_files(ws)
        set_workspace_path_override(Path(str(ws.root)))
        with TestClient(create_app(serve_static=False)) as client:
            response = client.get(
                "/api/workspace/context",
                params={
                    "projectId": exp.project.id,
                    "experimentId": exp.id,
                    "runId": run.id,
                },
            )
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        assert response.json()["focus"]["runId"] == run.id
        assert _workspace_files(ws) == before


class TestWorkspaceCacheRoutesRemoved:
    """arch-own-01-cleanup: the two routes that only read the never-written
    ``<root>/cache/`` are gone; the remote-mirror cache status route stays."""

    def test_no_cache_stats_route(self) -> None:
        paths = create_app(serve_static=False).openapi()["paths"]
        assert "/api/workspace/cache/stats" not in paths

    def test_no_cache_delete_route(self) -> None:
        paths = create_app(serve_static=False).openapi()["paths"]
        assert "delete" not in paths.get("/api/workspace/cache", {})

    def test_cache_status_route_kept(self) -> None:
        paths = create_app(serve_static=False).openapi()["paths"]
        assert "/api/workspace/cache/status" in paths


def _find_file(nodes: list[dict[str, object]], name: str) -> dict[str, object] | None:
    for node in nodes:
        if node.get("name") == name:
            return node
        children = node.get("children")
        if isinstance(children, list):
            found = _find_file(children, name)
            if found is not None:
                return found
    return None


class TestListWorkspaceFiles:
    def test_catalog_annotates_emitted_artifact(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            src = ctx.get_dir("work") / "result.json"
            src.write_bytes(b'{"t": 1}\n')
            artifact = ctx.emit_artifact(src, name="result.json", metadata={"task_id": "sim"})
        rel = Path(run.execution_dir("e01")).resolve().relative_to(Path(str(ws.root)).resolve())
        with served(ws) as client:
            response = client.get(
                "/api/workspace/files",
                params={"path": rel.as_posix(), "include": "catalog", "max_depth": 8},
            )
        assert response.status_code == 200, response.text
        node = _find_file(response.json()["children"], "result.json")
        assert node is not None
        assert node["assetId"] == artifact.id
        assert node["producerRunId"] == run.id

    def test_catalog_annotates_imported_payload(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        asset = ws.assets.import_asset("greeting", source, action="copy")
        payload = Path(ws.assets.payload_path(asset.id))
        parent = payload.resolve().relative_to(Path(str(ws.root)).resolve())
        with served(ws) as client:
            response = client.get(
                "/api/workspace/files",
                params={"path": parent.parent.as_posix(), "include": "catalog", "max_depth": 2},
            )
        assert response.status_code == 200, response.text
        node = _find_file(response.json()["children"], payload.name)
        assert node is not None
        assert node["assetId"] == asset.id
        assert node["assetKind"] == "asset"
        assert node["hasPreviewSidecar"] is False

    def test_info_counts_one_workspace_import(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        ws.assets.import_asset("greeting", source, action="copy")
        with served(ws) as client:
            response = client.get("/api/workspace/info")
        assert response.status_code == 200, response.text
        assert response.json()["assetCount"] == 1


class TestWorkspaceInfo:
    def test_unmigrated_legacy_asset_409(self, served, tmp_path: Path) -> None:
        from tests.support.legacy_assets import HELLO, LEGACY_ID, write_legacy_data_asset

        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
        )
        with served(ws, raise_server_exceptions=False) as client:
            blocked = client.get("/api/workspace/info")
        assert blocked.status_code == 409, blocked.text
        assert blocked.json()["error"]["code"] == "MIGRATION_REQUIRED"
        assert "molab migrate assets" in blocked.json()["error"]["message"]

        ws.assets.rewrite_legacy()
        with served(ws) as client:
            response = client.get("/api/workspace/info")
        assert response.status_code == 200, response.text
        assert response.json()["assetCount"] == 1


class TestReadWorkspaceFileBlob:
    """``/file/blob`` streams what a browser draws itself, and nothing that can script."""

    def _blob(self, tmp_path: Path, name: str, data: bytes) -> tuple[int, bytes, str]:
        client = _client(tmp_path)
        (tmp_path / "ws" / name).write_bytes(data)
        with client:
            response = client.get("/api/workspace/file/blob", params={"path": name})
        set_workspace_path_override(None)
        return response.status_code, response.content, response.headers.get("content-type", "")

    def test_streams_a_pdf(self, tmp_path: Path) -> None:
        status, body, media = self._blob(tmp_path, "fig.pdf", b"%PDF-1.5\n")
        assert status == 200
        assert body == b"%PDF-1.5\n"
        assert media == "application/pdf"

    def test_refuses_svg(self, tmp_path: Path) -> None:
        status, _, _ = self._blob(tmp_path, "fig.svg", b"<svg/>")
        assert status == 400
