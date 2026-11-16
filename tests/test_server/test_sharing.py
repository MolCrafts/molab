"""HTTP tests exercise the gateway's actual identity and route boundary."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from molab.server.sharing import create_sharing_app
from molab.sharing.settings import GatewaySettings


@pytest.fixture
def gateway(tmp_path):
    settings = GatewaySettings(
        issuer="cluster",
        proxy_key="gateway-key-" + "x" * 32,
        public_origin="https://lab.example/",
        state_dir=tmp_path / "control",
        local_state_confirmed=True,
    )
    app = create_sharing_app(settings)
    store = app.state.sharing_store
    alice = store.provision_principal("cluster", "alice", "Alice")
    bob = store.provision_principal("cluster", "bob", "Bob")
    _, token = store.provision_source(alice.id, "cluster-a", 1001)
    with TestClient(app) as client:
        yield client, store, alice, bob, token, settings


def headers(subject="alice"):
    return {
        "X-Molab-Proxy-Key": "gateway-key-" + "x" * 32,
        "X-Molab-Subject": subject,
        "Origin": "https://lab.example",
    }


def test_gateway_does_not_expose_workspace_or_plugin_surfaces(gateway):
    client, _, _, _, _, _ = gateway
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/sharing/me", headers=headers()).status_code == 200
    for path in (
        "/api/projects",
        "/api/workspace/files",
        "/api/molq/jobs",
        "/api/preview",
        "/api/auth/login",
        "/api/registry/plugins",
    ):
        assert client.get(path, headers=headers()).status_code == 404
    assert all(
        p.startswith(("/api/sharing/", "/internal/sharing/")) or p == "/api/health"
        for p in client.app.openapi()["paths"]
    )


def test_identity_headers_require_gateway_secret_and_provisioned_subject(gateway):
    client, _, _, _, token, _ = gateway
    assert client.get("/api/sharing/me").status_code == 401
    assert client.get("/api/sharing/me", headers={"X-Molab-Subject": "alice"}).status_code == 401
    assert client.get("/api/sharing/me", headers=headers("unknown")).status_code == 401
    assert (
        client.get(
            "/api/sharing/me",
            headers={**headers(), "Authorization": "Bearer " + token, "X-Molab-Proxy-Key": "wrong"},
        ).status_code
        == 401
    )
    assert (
        client.get("/api/sharing/projects", headers=headers()).headers["cache-control"]
        == "no-store"
    )


def test_real_http_invitation_revocation_and_request_validation(gateway):
    client, store, _, bob, token, _ = gateway
    source_headers = {"Authorization": "Bearer " + token}
    draft = client.post(
        "/internal/sharing/publications",
        headers=source_headers,
        json={"workspace_id": "w", "project": {"id": "p", "name": "P"}},
    )
    assert draft.status_code == 201, draft.text
    publication = draft.json()
    version = publication["version_id"]
    assert (
        client.put(
            f"/internal/sharing/publications/{version}/batches/0",
            headers=source_headers,
            json={"experiments": [{"id": "e", "name": "E"}]},
        ).status_code
        == 204
    )
    assert (
        client.post(
            f"/internal/sharing/publications/{version}/commit", headers=source_headers
        ).status_code
        == 200
    )
    project = publication["project_id"]
    path = f"/api/sharing/projects/{project}/invitations"
    assert (
        client.post(
            path,
            headers={**headers(), "Origin": "https://evil.example"},
            json={"recipient_id": bob.id},
        ).status_code
        == 403
    )
    invite = client.post(path, headers=headers(), json={"recipient_id": bob.id})
    assert invite.status_code == 201
    with sqlite3.connect(store.path) as connection:
        audit = connection.execute(
            "SELECT request_id, result FROM audit_events WHERE action = 'invitation.created' AND object_id = ?",
            (invite.json()["id"],),
        ).fetchone()
        assert audit == (invite.headers["x-request-id"], "success")
    assert (
        client.post(
            f"/api/sharing/invitations/{invite.json()['id']}/accept", headers=headers("bob")
        ).status_code
        == 204
    )
    assert client.get(f"/api/sharing/projects/{project}", headers=headers("bob")).status_code == 200
    assert (
        client.get(
            f"/api/sharing/projects/{project}/runs?limit=-1", headers=headers("bob")
        ).status_code
        == 422
    )
    assert (
        client.delete(
            f"/api/sharing/projects/{project}/members/{bob.id}", headers=headers()
        ).status_code
        == 204
    )
    assert client.get(f"/api/sharing/projects/{project}", headers=headers("bob")).status_code == 404
    bad = client.post(
        "/internal/sharing/publications",
        headers=source_headers,
        json={"workspace_id": "w", "project": {"id": "x", "name": "X", "secret": "do-not-echo"}},
    )
    assert bad.status_code == 422
    assert "do-not-echo" not in bad.text


def test_oversize_body_is_rejected_even_without_content_length(gateway):
    client, _, _, _, token, _ = gateway
    response = client.post(
        "/internal/sharing/publications",
        headers={"Authorization": "Bearer " + token},
        content=iter([b" " * 1024 * 1024] * 3),
    )
    assert response.status_code == 413


def test_gateway_never_discovers_server_plugins(tmp_path, monkeypatch):
    def forbidden():
        pytest.fail("gateway must not discover or start plugins")

    monkeypatch.setattr("molab.plugins.discover_server_plugins", forbidden)
    settings = GatewaySettings(
        issuer="cluster",
        proxy_key="gateway-key-" + "x" * 32,
        public_origin="https://lab.example/",
        state_dir=tmp_path / "gateway",
        local_state_confirmed=True,
    )
    app = create_sharing_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


def test_shared_static_assets_cannot_read_outside_the_bundle(tmp_path):
    from molab.server.app import create_app

    web = tmp_path / "bundle"
    web.mkdir()
    (web / "index.html").write_text("UI")
    secret = tmp_path / "secret"
    secret.write_text("PRIVATE-STATIC-SECRET")
    (web / "escape").symlink_to(secret)
    app = create_app(static_dir=web)
    with TestClient(app) as client:
        assert client.get("/escape").status_code == 404
        escaped = client.get("/%2e%2e/secret")
        assert escaped.status_code == 404
        assert "PRIVATE-STATIC-SECRET" not in escaped.text
