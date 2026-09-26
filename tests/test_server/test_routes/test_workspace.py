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
        assert response.json()["knowledge"] == [_IDEA_GOLDEN]

    def test_copilot_reports_the_same_knowledge(self, tmp_path: Path) -> None:
        client = _client(tmp_path, with_note=True)
        with client:
            response = client.get("/api/workspace/copilot")
        set_workspace_path_override(None)
        assert response.status_code == 200, response.text
        assert response.json()["relevantKnowledge"] == [_IDEA_GOLDEN]

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
