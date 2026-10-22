"""HTTP transfer uses scoped molq I/O, bounded reads and disk staging."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from molq import Molq, MolqError

from molab.server.app import create_app
from molab.server.dependencies import get_workspace
from molab.workspace import Workspace
from molab.workspace.fs_cached import CachedRemoteFileSystem
from molab.workspace.fs_remote import RemoteFileSystem


@pytest.fixture
def remote_client(tmp_path, monkeypatch):
    root = tmp_path / "remote"
    workspace = Workspace(root)
    workspace.materialize()
    with Molq(registry=tmp_path / "registry.db") as molq:
        cluster = molq.clusters.register(
            name="files", scheduler="shell", target_root=str(tmp_path / "jobs")
        )
        inner = RemoteFileSystem(molq, cluster.name, str(root))
        fs = CachedRemoteFileSystem(inner, mirror_root=tmp_path / "mirror")
        remote = Workspace(str(root), fs=fs)
        monkeypatch.setattr("molab.workspace.connection.get_client", lambda _registry=None: molq)
        app = create_app(serve_static=False)
        app.dependency_overrides[get_workspace] = lambda: remote
        with TestClient(app) as client:
            yield client, root, fs, inner


def test_upload_publishes_and_download_uses_bounded_ranges(remote_client, monkeypatch):
    client, root, fs, inner = remote_client
    payload = b"content\x00" * 150000
    response = client.post(
        "/api/workspace/file/upload", params={"path": "data.bin"}, content=payload
    )
    assert response.status_code == 204, response.text
    assert (root / "data.bin").read_bytes() == payload
    assert not list(root.glob(".molab-upload-*"))
    ranges = []
    read_range = inner.read_range

    def bounded(path, offset, length):
        assert length <= 262144
        ranges.append((offset, length))
        return read_range(path, offset, length)

    monkeypatch.setattr(inner, "read_range", bounded)
    monkeypatch.setattr(
        fs, "read_bytes", lambda _path: pytest.fail("download buffered the complete file")
    )
    response = client.get("/api/workspace/file/blob", params={"path": "data.bin", "download": True})
    assert response.status_code == 200 and response.content == payload
    assert len(ranges) > 1
    assert response.headers["content-disposition"].startswith("attachment;")
    assert client.get("/api/workspace/file/blob", params={"path": "data.bin"}).status_code == 400


def test_scope_rejects_parent_traversal_and_escaping_symlink(remote_client):
    client, root, _, _ = remote_client
    outside = root.parent / "outside"
    outside.write_bytes(b"private")
    (root / "escape").symlink_to(outside)
    assert client.get("/api/workspace/file", params={"path": "../outside"}).status_code == 400
    assert client.get("/api/workspace/file", params={"path": "escape"}).status_code == 403
    response = client.post(
        "/api/workspace/file/upload", params={"path": "escape"}, content=b"overwrite"
    )
    assert response.status_code == 403, response.text
    assert outside.read_bytes() == b"private"


def test_uncertain_upload_is_reported_without_resending(remote_client, monkeypatch):
    client, _, _, inner = remote_client
    calls = []

    def uncertain(*args: object, **_kwargs: object):
        calls.append(args)
        raise MolqError("OUTCOME_UNKNOWN", "Transfer outcome is uncertain", outcome="unknown")

    monkeypatch.setattr(inner, "upload", uncertain)
    response = client.post("/api/workspace/file/upload", params={"path": "file"}, content=b"data")
    assert response.status_code == 409
    assert response.json()["error"]["outcome"] == "unknown" and len(calls) == 1


def test_workspace_allowlist_is_checked_for_file_upload_and_download(tmp_path, monkeypatch):
    from molab.server.deps import resolution
    from molab.server.deps.auth import get_optional_user
    from molab.services.auth import set_auth_enabled
    from molab.services.auth.models import AuthUser

    workspace = Workspace(tmp_path / "workspace")
    workspace.materialize()
    user = AuthUser(
        username="reader",
        password_hash="unused",
        role="operator",
        workspaces=["allowed"],
        created_at="",
        updated_at="",
    )
    monkeypatch.setattr(resolution, "get_workspace_by_key", lambda _key: workspace)
    app = create_app(serve_static=False)
    app.dependency_overrides[get_optional_user] = lambda: user
    set_auth_enabled(True)
    try:
        with TestClient(app) as client:
            assert (
                client.get(
                    "/api/workspace/file", params={"ws": "forbidden", "path": "workspace.json"}
                ).status_code
                == 403
            )
            response = client.post(
                "/api/workspace/file/upload",
                params={"ws": "forbidden", "path": "file"},
                content=b"data",
            )
            assert response.status_code == 403 and not (tmp_path / "workspace" / "file").exists()
            assert (
                client.get(
                    "/api/workspace/file", params={"ws": "allowed", "path": "workspace.json"}
                ).status_code
                == 200
            )
    finally:
        set_auth_enabled(False)


def test_editor_and_directory_operations_use_the_same_scoped_filesystem(remote_client, monkeypatch):
    client, root, fs, _ = remote_client
    writes = []
    write = fs.atomic_write_text

    def record_write(path, content, **kwargs: object):
        writes.append(path)
        return write(path, content, **kwargs)

    monkeypatch.setattr(fs, "atomic_write_text", record_write)
    response = client.post(
        "/api/workspace/directories", json={"folder_id": "workspace", "path": "inputs"}
    )
    assert response.status_code == 200
    response = client.put(
        "/api/workspace/files",
        json={"folder_id": "workspace", "path": "inputs/config.json", "content": "{}"},
    )
    assert response.status_code == 200 and writes == [str(root / "inputs" / "config.json")]
    assert (root / "inputs" / "config.json").read_text() == "{}"


def test_custom_cache_directory_still_namespaces_destination_and_root(remote_client, tmp_path):
    from molab.server.workspace_targets import (
        WorkspaceTarget,
        target_to_filesystem_for_workspace_target,
    )
    from molab.workspace.connection import get_client

    _, root, _, inner = remote_client
    registry = get_client().rpc("molq.hello")["registry_id"]
    targets = [
        WorkspaceTarget(
            name=f"root-{i}",
            registry_id=registry,
            cluster_id=inner.cluster_id,
            root_path=str(root / str(i)),
            cache_dir=str(tmp_path / "shared-cache"),
        )
        for i in range(2)
    ]
    mirrors = [target_to_filesystem_for_workspace_target(target).mirror_root for target in targets]
    assert mirrors[0] != mirrors[1] and all(
        path.parent == tmp_path / "shared-cache" for path in mirrors
    )


def test_file_auth_failure_requests_workspace_otp_without_invalidating_web_login(
    remote_client, monkeypatch
):
    client, root, _, inner = remote_client
    (root / "file.txt").write_text("data")

    def expired(_path):
        raise MolqError("AUTH_REQUIRED", "SSH authentication required")

    monkeypatch.setattr(inner, "read_bytes", expired)
    response = client.get("/api/workspace/file", params={"path": "file.txt", "ws": "remote"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["details"] == {"workspace": "remote", "reason": "needs_auth"}


@pytest.mark.parametrize("diagnostic", [None, "SSH control socket could not be created"])
def test_connect_preserves_authentication_transport_failure(remote_client, monkeypatch, diagnostic):
    from types import SimpleNamespace

    from molab.server.routes import workspaces

    client, _, _, _ = remote_client

    def authenticate(_code):
        raise MolqError(
            "TRANSPORT_UNAVAILABLE", "Cannot create authentication helper", diagnostic=diagnostic
        )

    monkeypatch.setattr(
        workspaces,
        "_cluster_for_served_key",
        lambda _key: (SimpleNamespace(authenticate=authenticate), "cluster"),
    )
    response = client.post("/api/workspaces/remote/connect", json={"code": "fixture"})
    assert response.status_code == 502
    assert response.json()["detail"] == (
        f"Authentication connection failed: {diagnostic or 'Cannot create authentication helper'}"
    )


def test_connect_distinguishes_root_access_failure_from_authentication(remote_client, monkeypatch):
    from types import SimpleNamespace

    from molab.server.exceptions import RemoteWorkspaceUnreachableError
    from molab.server.routes import workspaces

    client, _, _, _ = remote_client
    monkeypatch.setattr(
        workspaces,
        "_cluster_for_served_key",
        lambda _key: (SimpleNamespace(authenticate=lambda _code: None), "cluster"),
    )

    def inaccessible(_key):
        raise RemoteWorkspaceUnreachableError("remote", "unreachable") from ValueError(
            "Unsupported entity metadata"
        )

    monkeypatch.setattr(workspaces, "get_workspace_by_key", inaccessible)
    response = client.post("/api/workspaces/remote/connect", json={"code": "fixture"})
    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Connected, but cannot read this root: Unsupported entity metadata"
    )
