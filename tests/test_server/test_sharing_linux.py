"""Actual kernel/user boundaries. Run separately as root on a Linux test host.

Root is used only by the test to create disposable UIDs, then permanently
dropped in each child. The application never launches privileged workers.
"""

import json
import multiprocessing
import os
import sys
import traceback
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from molq import Molq

from molab.server.sharing_worker import create_managed_app
from molab.sharing.publisher import Publisher
from molab.sharing.settings import WorkerSettings
from molab.workspace import Workspace, connection

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or os.geteuid() != 0,
    reason="requires a disposable Linux test host with permission to create two UIDs",
)


def _probe_user(uid, own_root, other_root, pipe):
    try:
        from molab.services import operator_config

        operator_config.OPERATOR_CONFIG_PATH = own_root / "operator.json"
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
        # setuid does not change an inherited HOME. Configure the real Molq
        # process explicitly so it cannot use the parent's private registry.
        config = own_root / "molq.json"
        config.write_text("{}")
        registry = own_root / "registry.sqlite3"
        patch = pytest.MonkeyPatch()
        patch.setattr(connection, "Molq", partial(Molq, config=config, registry=registry))
        settings = WorkerSettings(
            issuer="cluster",
            subject=f"user-{uid}",
            principal_id=f"principal-{uid}",
            uid=uid,
            cluster_id="cluster",
            proxy_key=f"user-key-{uid}-" + "x" * 32,
            public_origin="http://localhost/",
            gateway_url="http://localhost/",
            source_token="source." + "x" * 32,
        )
        application = create_managed_app(own_root, settings)
        trusted = {
            "X-Molab-Subject": f"user-{uid}",
            "X-Molab-Proxy-Key": f"user-key-{uid}-" + "x" * 32,
        }
        try:
            (other_root / "secret").read_text()
            other_read_denied = False
        except PermissionError:
            other_read_denied = True
        with TestClient(application) as client:
            own = client.get("/api/sharing/worker", headers=trusted)
            forged = client.get(
                "/api/projects", headers={**trusted, "X-Molab-Subject": "other-user"}
            )
            own_projects = client.get("/api/projects", headers=trusted)
        pipe.send(
            {
                "uid": os.getuid(),
                "own_uid": own.json().get("uid"),
                "own_status": own_projects.status_code,
                "registry_uid": registry.stat().st_uid,
                "other_read_denied": other_read_denied,
                "forged_status": forged.status_code,
            }
        )
    except BaseException as exc:
        pipe.send({"error": str(exc), "traceback": traceback.format_exc()})
    finally:
        pipe.close()


def test_two_real_user_services_cannot_borrow_each_others_identity(monkeypatch):
    import pwd

    monkeypatch.setattr("molab.plugins.discover_server_plugins", list)
    monkeypatch.setattr(Publisher, "verify_source", lambda _self: "source")
    # Load the ASGI test transport/backend before dropping UID. CI's Python
    # download cache may be owner-only; the child must not need to import it.
    with TestClient(FastAPI()) as warmup:
        assert warmup.get("/").status_code == 404
    connection.close_client()
    context = multiprocessing.get_context("fork")
    with TemporaryDirectory(prefix="molab-multiuid-", dir="/tmp") as directory:
        base = Path(directory)
        base.chmod(0o755)
        roots = [base / "alice", base / "bob"]
        uids = [60101, 60102]
        for uid in uids:
            try:
                pwd.getpwuid(uid)
            except KeyError:
                continue
            pytest.fail("multi-UID probes require unused disposable UIDs")
        for root, uid in zip(roots, uids, strict=True):
            root.mkdir(mode=0o700)
            ws = Workspace(root, name=f"user-{uid}")
            ws.materialize()
            ws.add_project("private-project")
            (root / "secret").write_text("private credentials")
            for entry in [root, *root.rglob("*")]:
                os.chown(entry, uid, uid)
        for index, uid in enumerate(uids):
            parent, child = context.Pipe(duplex=False)
            process = context.Process(
                target=_probe_user, args=(uid, roots[index], roots[1 - index], child)
            )
            process.start()
            child.close()
            process.join(timeout=20)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                pytest.fail("fixed-UID service did not complete")
            assert process.exitcode == 0
            result = parent.recv()
            parent.close()
            assert result == {
                "uid": uid,
                "own_uid": uid,
                "own_status": 200,
                "registry_uid": uid,
                "other_read_denied": True,
                "forged_status": 403,
            }, json.dumps(result)
