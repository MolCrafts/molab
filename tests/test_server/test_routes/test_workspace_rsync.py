"""POST /api/workspace/rsync copies a remote root; local roots have no mirror."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.dependencies import get_workspace
from molab.workspace import Workspace
from molab.workspace.fs_remote import rsync_options


def test_rsync_options_put_includes_before_excludes() -> None:
    assert rsync_options(
        include=["*.json", ""],
        exclude=["out/**"],
        delete=True,
        dry_run=True,
    ) == ["-a", "--include=*.json", "--exclude=out/**", "--delete", "--dry-run"]


@pytest.fixture
def local_client(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.materialize()
    app = create_app(serve_static=False)
    app.dependency_overrides[get_workspace] = lambda: workspace
    with TestClient(app) as client:
        yield client


def test_local_workspace_has_no_sync_rules_and_no_flag_route(local_client) -> None:
    assert local_client.get("/api/workspace/sync-rules").status_code == 409
    assert local_client.post("/api/workspace/rsync", json={"direction": "pull"}).status_code == 404
