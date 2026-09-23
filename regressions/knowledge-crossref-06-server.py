"""Public-API goldens for knowledge-crossref-06-server.

Hard-coded: the projected knowledge row for a seeded Note **file**
(``knowledges/idea.md``) as ``GET /api/workspace/context`` reports it, the 404 a
missing concept path still maps to, and the source-level redirect (the three
route modules no longer name ``molab.workspace.bundle``, and
``routes/workspace.py`` consumes the services projection). The workspace is
in-process (``Workspace(...).materialize()`` + a Note file) — no third-party
runtime, no network.
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from molab.knowledge import Note
from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.server.routes import knowledge as knowledge_routes
from molab.server.routes import run as run_routes
from molab.server.routes import workspace as workspace_routes
from molab.workspace import Workspace

_IDEA_GOLDEN = [{"path": "knowledges/idea.md", "type": "Note", "title": "Idea", "id": "idea"}]


def _check_redirect_sources() -> None:
    """No route reaches knowledge through a workspace shim."""
    for module in (knowledge_routes, run_routes, workspace_routes):
        src = inspect.getsource(module)
        assert "molab.workspace.bundle" not in src, module.__name__
    assert "molab.workspace.knowledge" not in inspect.getsource(knowledge_routes)
    assert "molab.workspace.knowledge" not in inspect.getsource(run_routes)
    for handler in (
        workspace_routes.get_workspace_context,
        workspace_routes.get_workspace_copilot,
    ):
        src = inspect.getsource(handler)
        assert "molab.services.knowledge_context" in src
        assert "context_with_knowledge" in src


def main() -> None:
    _check_redirect_sources()

    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()
        Note(Path(str(workspace.root)) / "knowledges" / "idea").write("# Idea\n")

        set_workspace_path_override(Path(str(workspace.root)))
        try:
            with TestClient(create_app(serve_static=False)) as client:
                context = client.get("/api/workspace/context")
                assert context.status_code == 200, context.text
                assert context.json()["knowledge"] == _IDEA_GOLDEN

                missing = client.get("/api/knowledge/note", params={"path": "knowledges/nope"})
                assert missing.status_code == 404, missing.text
        finally:
            set_workspace_path_override(None)


if __name__ == "__main__":
    main()
