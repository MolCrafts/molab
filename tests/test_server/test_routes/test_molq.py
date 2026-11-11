"""Registry-wide operations require unrestricted workspace access."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from molq import MolqError

from molab.server.app import create_app
from molab.server.deps.auth import get_optional_user
from molab.services.auth import set_auth_enabled
from molab.services.auth.models import AuthUser


@pytest.mark.parametrize(
    "path",
    [
        "/destinations",
        "/targets",
        "/jobs",
        "/jobs/1?target=private",
        "/jobs/1/logs?target=private",
    ],
)
def test_restricted_user_cannot_access_registry_operations(path):
    app = create_app(serve_static=False)
    app.dependency_overrides[get_optional_user] = lambda: AuthUser(
        username="limited",
        password_hash="unused",
        role="viewer",
        workspaces=["allowed"],
        created_at="",
        updated_at="",
    )
    set_auth_enabled(True)
    try:
        with TestClient(app) as client:
            assert client.get("/api/plugins/molq" + path).status_code == 403
    finally:
        set_auth_enabled(False)


@pytest.mark.parametrize(
    "kind,status", [("AUTH_REQUIRED", 503), ("CONNECTION_TIMEOUT", 504), ("NOT_FOUND", 404)]
)
@pytest.mark.parametrize("suffix", ["", "/logs"])
def test_job_errors_preserve_classification(monkeypatch, kind, status, suffix):
    from molab.server.routes import molq

    def fail(*_args: object):
        raise MolqError(kind, "test failure")

    monkeypatch.setattr(molq.dashboard, "get_job", fail)
    with TestClient(create_app(serve_static=False)) as client:
        response = client.get("/api/plugins/molq/jobs/1" + suffix, params={"target": "demo"})
    assert response.status_code == status


@pytest.mark.parametrize("partial,status", [(False, 404), (True, 502)])
@pytest.mark.parametrize("suffix", ["", "/logs"])
def test_actual_dashboard_missing_and_partial_queue(monkeypatch, partial, status, suffix):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from molab.server.routes import molq

    mq = SimpleNamespace(
        clusters=SimpleNamespace(list=lambda: [{"name": "demo", "id": "demo-id"}]),
        cluster=lambda _name: SimpleNamespace(
            list=lambda **_kwargs: {
                "snapshots": [],
                "coverage": {"errors": ["down"] if partial else []},
            }
        ),
    )
    monkeypatch.setattr(molq.dashboard, "molq_session", lambda *_args: nullcontext(mq))
    with TestClient(create_app(serve_static=False)) as client:
        response = client.get("/api/plugins/molq/jobs/missing" + suffix, params={"target": "demo"})
    assert response.status_code == status
