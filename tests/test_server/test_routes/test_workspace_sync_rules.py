"""Sync-rule routes translate the form. They do not accept rsync flags."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from molq import Molq

from molab.server.app import create_app
from molab.server.dependencies import get_workspace
from molab.workspace import Workspace
from molab.workspace.fs_cached import CachedRemoteFS
from molab.workspace.fs_remote import RemoteFS
from molab.workspace.sync_rules import exclusive_transfer


@pytest.fixture
def remote_client(tmp_path, monkeypatch):
    root = tmp_path / "remote"
    workspace = Workspace(root)
    workspace.materialize()
    with Molq(registry=tmp_path / "registry.db") as molq:
        cluster = molq.clusters.register(
            name="files", scheduler="shell", target_root=str(tmp_path / "jobs")
        )
        inner = RemoteFS(molq, cluster.name, str(root))
        fs = CachedRemoteFS(inner, mirror_root=tmp_path / "mirror")
        remote = Workspace(str(root), fs=fs)
        monkeypatch.setattr("molab.workspace.connection.get_client", lambda _registry=None: molq)
        app = create_app(serve_static=False)
        app.dependency_overrides[get_workspace] = lambda: remote
        with TestClient(app) as client:
            yield client, root, fs


def test_save_preview_and_run_one_rule_per_path(remote_client, monkeypatch) -> None:
    client, root, fs = remote_client
    seen: dict[str, object] = {}

    def fake_rsync(remote_root: str, **kwargs: object) -> dict[str, object]:
        seen["remote"] = remote_root
        seen["kwargs"] = kwargs
        return {"output": "note.md\n", "direction": kwargs["direction"]}

    monkeypatch.setattr(fs, "rsync", fake_rsync)
    saved = client.post(
        "/api/workspace/sync-rules",
        json={
            "path": str(root / "experiments"),
            "kind": "directory",
            "content": "records",
            "extraFiles": "remove",
            "direction": "pull",
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["path"] == "experiments"
    assert body["extraFiles"] == "remove"
    assert body["lastRunAt"] is None
    again = client.post(
        "/api/workspace/sync-rules",
        json={
            "path": "experiments",
            "kind": "directory",
            "content": "records",
            "extraFiles": "remove",
        },
    )
    assert again.json()["id"] == body["id"]

    preview = client.post(f"/api/workspace/sync-rules/{body['id']}/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["dryRun"] is True
    assert preview.json()["output"] == "note.md\n"
    assert client.get("/api/workspace/sync-rules").json()["rules"][0]["lastRunAt"] is None
    assert seen["kwargs"]["dry_run"] is True
    assert seen["kwargs"]["delete"] is True
    assert seen["kwargs"]["include"][0] == "*/"
    assert seen["remote"] == f"{root}/experiments"

    ran = client.post(f"/api/workspace/sync-rules/{body['id']}/run")
    assert ran.status_code == 200, ran.text
    assert ran.json()["rule"]["lastStatus"] == "ok"
    assert ran.json()["rule"]["lastRunAt"]
    assert ran.json()["dryRun"] is False


def test_rules_reject_escape_short_intervals_and_flag_fields(remote_client) -> None:
    client, root, _fs = remote_client
    escaped = client.post(
        "/api/workspace/sync-rules",
        json={"path": "../secret", "kind": "directory"},
    )
    assert escaped.status_code == 422, escaped.text
    outside = client.post(
        "/api/workspace/sync-rules",
        json={"path": "/etc/passwd", "kind": "file"},
    )
    assert outside.status_code == 422, outside.text
    too_soon = client.post(
        "/api/workspace/sync-rules",
        json={"path": "logs", "kind": "directory", "when": "interval", "intervalMinutes": 4},
    )
    assert too_soon.status_code == 422, too_soon.text
    file_rule = client.post(
        "/api/workspace/sync-rules",
        json={
            "path": str(root / "note.md"),
            "kind": "file",
            "content": "records",
            "extraFiles": "remove",
        },
    )
    assert file_rule.status_code == 200, file_rule.text
    assert file_rule.json()["path"] == "note.md"
    assert file_rule.json()["content"] == "everything"
    assert file_rule.json()["extraFiles"] == "keep"
    flags = client.post(
        "/api/workspace/sync-rules",
        json={"path": "note.md", "kind": "file", "include": ["--delete"]},
    )
    assert flags.status_code == 200, flags.text
    assert "include" not in flags.json()


def test_run_reports_a_busy_mirror_and_delete_removes_the_rule(remote_client) -> None:
    client, _root, fs = remote_client
    saved = client.post(
        "/api/workspace/sync-rules",
        json={"path": "note.md", "kind": "file"},
    )
    assert saved.status_code == 200, saved.text
    rule_id = saved.json()["id"]
    with exclusive_transfer(fs.mirror_root):
        busy = client.post(f"/api/workspace/sync-rules/{rule_id}/run")
    assert busy.status_code == 409, busy.text
    missing = client.post("/api/workspace/sync-rules/missing/run")
    assert missing.status_code == 404
    assert client.delete(f"/api/workspace/sync-rules/{rule_id}").status_code == 204
    assert client.get("/api/workspace/sync-rules").json()["rules"] == []
