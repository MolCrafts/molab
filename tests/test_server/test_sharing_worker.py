"""Owner projection, real HTTP publication, and fixed-UID worker isolation."""

import os
import subprocess
import sys
from contextlib import nullcontext
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import Mock

import pytest
from _live_server import LiveServer
from fastapi import FastAPI, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from molab.ids import compute_definition_hash
from molab.server.dependencies import set_served_workspaces, set_workspace_path_override
from molab.server.sharing import create_sharing_app
from molab.server.sharing_worker import create_managed_app
from molab.sharing.models import PublicationSelection
from molab.sharing.publisher import Publisher, build_preview
from molab.sharing.settings import GatewaySettings, WorkerSettings, read_private_config
from molab.sharing.store import SharingError
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.refs import ref_of


@pytest.fixture
def publication_workspace(tmp_path):
    ws = Workspace(tmp_path / "private", name="Alice workspace")
    ws.materialize()
    p = ws.add_project("Research")
    selected = p.add_experiment("Selected")
    unselected = p.add_experiment("PRIVATE-EXPERIMENT")
    run = selected.add_run(params={"temperature": 300, "credential": "PRIVATE-TOKEN"})
    unselected.add_run(params={"credential": "ANOTHER-PRIVATE-TOKEN"})
    with run.start() as ctx:
        ctx.metrics.scalar("energy", -1.2, 0)
        ctx.metrics.text("note", "PRIVATE-LOG")
        ctx.mark_succeeded()
    (Path(str(run.run_dir)) / "result.py").write_text("raise RuntimeError('SIDECAR EXECUTED')\n")
    selection = PublicationSelection(
        project_id=p.id,
        experiment_ids=[selected.id],
        run_refs=[str(ref_of(run))],
        parameter_keys=["temperature"],
        metric_keys=["energy"],
    )
    return ws, p, selected, run, selection


def worker_settings(**changes: object):
    values = {
        "issuer": "cluster",
        "proxy_key": "worker-key-" + "x" * 32,
        "public_origin": "https://lab.example/",
        "principal_id": "alice-id",
        "subject": "alice",
        "uid": os.getuid(),
        "cluster_id": "cluster-a",
        "gateway_url": "http://127.0.0.1/",
        "source_token": "source." + "x" * 32,
    }
    return WorkerSettings.model_validate({**values, **changes})


def test_projection_excludes_private_fields_and_never_loads_sidecars(publication_workspace):
    ws, _, _, run, selection = publication_workspace
    preview = build_preview(ws, selection)
    raw = preview.model_dump_json()
    for secret in (
        "PRIVATE-TOKEN",
        "PRIVATE-EXPERIMENT",
        "PRIVATE-LOG",
        str(ws.root),
        "credential",
        "result.py",
    ):
        assert secret not in raw
    assert preview.runs[0].name == run.id
    assert preview.runs[0].parameters == {"temperature": 300}
    assert preview.runs[0].metrics["energy"][0].value == -1.2


def test_actual_network_publish_refresh_stop_and_selection_boundary(
    tmp_path, publication_workspace
):
    ws, project, exp, run, selection = publication_workspace
    app = create_sharing_app(
        GatewaySettings(
            issuer="cluster",
            proxy_key="gateway-key-" + "x" * 32,
            public_origin="https://lab.example/",
            state_dir=tmp_path / "gateway",
            local_state_confirmed=True,
        )
    )
    store = app.state.sharing_store
    alice = store.provision_principal("cluster", "alice", "Alice")
    bob = store.provision_principal("cluster", "bob", "Bob")
    _, token = store.provision_source(alice.id, "cluster-a", os.getuid())
    with LiveServer(app) as server:
        publisher = Publisher(
            ws,
            worker_settings(
                principal_id=alice.id, source_token=token, gateway_url=server.base + "/"
            ),
        )
        preview = build_preview(ws, selection)
        with pytest.raises(SharingError, match="Preview changed"):
            publisher.publish(selection, "unreviewed")
        result = publisher.publish(
            selection, compute_definition_hash(preview.model_dump(mode="json"))
        )
        invitation = store.invite(alice.id, result["project_id"], bob.id)
        store.respond(bob.id, invitation["id"], accept=True)
        first = store.get_project(bob.id, result["project_id"])
        publisher.refresh_all()
        assert store.get_project(bob.id, result["project_id"])["version_id"] == first["version_id"]
        exp.add_run(params={"credential": "NEW-PRIVATE-RUN"})
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            ctx.metrics.scalar("energy", -2.4, 1)
            ctx.mark_succeeded()
        publisher.refresh_all()
        assert store.objects(bob.id, result["project_id"], "run")["total"] == 1
        assert (
            store.metrics(bob.id, result["project_id"], exp.id, run.id)["metrics"]["energy"][0][
                "value"
            ]
            == -2.4
        )
        ws.remove_project(project.id)
        publisher.refresh_all()
        assert store.get_project(bob.id, result["project_id"])["active"] is True
        store.stop_publication(alice.id, result["project_id"])
        publisher.refresh_all()
        assert store.get_project(alice.id, result["project_id"])["active"] is False
        with pytest.raises(SharingError):
            store.get_project(bob.id, result["project_id"])


def test_worker_requires_fixed_owner_for_all_private_and_plugin_routes(
    monkeypatch, publication_workspace
):
    ws, _, _, _, selection = publication_workspace
    monkeypatch.setattr(Publisher, "verify_source", lambda _self: "source")
    monkeypatch.setattr("molab.plugins.discover_server_plugins", list)
    app = create_managed_app(Path(str(ws.root)), worker_settings())
    connected = []

    @app.websocket("/api/test-socket")
    async def test_socket(socket: WebSocket):
        connected.append(True)
        await socket.accept()
        await socket.send_json({"owner": "alice"})
        await socket.close()

    trusted = {
        "X-Molab-Proxy-Key": "worker-key-" + "x" * 32,
        "X-Molab-Subject": "alice",
        "Origin": "https://lab.example",
    }
    try:
        with TestClient(app) as client:
            with (
                pytest.raises(WebSocketDisconnect) as denied,
                client.websocket_connect(
                    "/api/test-socket", headers={**trusted, "X-Molab-Subject": "bob"}
                ),
            ):
                pass
            assert denied.value.code == 1008 and not connected
            with (
                pytest.raises(WebSocketDisconnect),
                client.websocket_connect(
                    "/api/test-socket", headers={**trusted, "Origin": "https://evil.example"}
                ),
            ):
                pass
            with client.websocket_connect("/api/test-socket", headers=trusted) as socket:
                assert socket.receive_json() == {"owner": "alice"}
            assert client.get("/api/projects").status_code == 401
            assert (
                client.get(
                    "/api/projects", headers={**trusted, "Origin": "http://localhost:5173"}
                ).status_code
                == 403
            )
            assert (
                client.get(
                    "/api/projects", headers={**trusted, "Sec-Fetch-Site": "same-site"}
                ).status_code
                == 403
            )
            assert (
                client.get(
                    "/api/projects", headers={**trusted, "X-Molab-Subject": "bob"}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/sharing/worker/preview",
                    headers={**trusted, "X-Molab-Subject": "bob"},
                    json=selection.model_dump(),
                ).status_code
                == 403
            )
            assert (
                client.get(
                    "/api/registry/plugins", headers={**trusted, "X-Molab-Subject": "bob"}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/sharing/worker/preview", headers=trusted, json=selection.model_dump()
                ).status_code
                == 200
            )
            identity = client.get("/api/sharing/worker", headers=trusted)
            assert identity.status_code == 200
            assert "source_token" not in identity.text and "proxy_key" not in identity.text
            assert (
                client.post(
                    "/api/projects",
                    headers={**trusted, "Origin": "https://evil.example"},
                    json={"name": "injected"},
                ).status_code
                == 403
            )
    finally:
        set_workspace_path_override(None)
        set_served_workspaces([])


def test_wrong_uid_and_public_config_are_rejected(monkeypatch, tmp_path):
    settings = worker_settings(uid=os.getuid() + 1)
    with pytest.raises(ValueError, match="configured"):
        settings.assert_uid()
    with monkeypatch.context() as elevated:
        elevated.setattr(os, "geteuid", lambda: os.getuid() + 1)
        with pytest.raises(ValueError, match="configured"):
            worker_settings().assert_uid()
    config = tmp_path / "config.json"
    config.write_text("{}")
    config.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        read_private_config(config)
    config.chmod(0o600)
    assert read_private_config(config) == "{}"
    link = tmp_path / "link.json"
    link.symlink_to(config)
    with pytest.raises(OSError):
        read_private_config(link)


def test_publisher_never_forwards_credentials_on_redirect(publication_workspace):
    ws, _, _, _, _ = publication_workspace
    receiver = FastAPI()
    captured = []

    @receiver.get("/api/health")
    def health():
        return {"status": "ok"}

    @receiver.get("/capture")
    def capture():
        captured.append(True)
        return {}

    with LiveServer(receiver) as other:
        redirector = FastAPI()
        redirector.get("/api/health")(health)

        @redirector.get("/internal/sharing/source")
        def redirect():
            return RedirectResponse(other.base + "/capture")

        with LiveServer(redirector) as server:
            publisher = Publisher(ws, worker_settings(gateway_url=server.base + "/"))
            with pytest.raises(SharingError):
                publisher.verify_source()
    assert not captured


def test_nonregular_config_is_rejected_without_waiting_for_a_writer(tmp_path):
    fifo = tmp_path / "config-pipe"
    os.mkfifo(fifo, 0o600)
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from molab.sharing.settings import read_private_config; read_private_config(Path(sys.argv[1]))",
            str(fifo),
        ],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    assert process.returncode != 0
    assert "must be a regular file" in process.stderr


def test_truncated_gateway_response_is_a_recoverable_sharing_error(
    publication_workspace, monkeypatch
):
    ws, _, _, _, _ = publication_workspace
    publisher = Publisher(ws, worker_settings())
    response = Mock()
    response.read.side_effect = IncompleteRead(b"partial", 100)
    opener = Mock()
    opener.open.return_value = nullcontext(response)
    monkeypatch.setattr(publisher, "_opener", opener)
    with pytest.raises(SharingError) as failure:
        publisher.request("GET", "/internal/sharing/source")
    assert failure.value.status == 502
