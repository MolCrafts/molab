"""Asset reads are answered from the snapshot, not by re-walking (P3-3d).

Before the read model, ``GET /assets/{id}`` scanned every manifest in the
workspace to find one row, and ``/lineage`` did that once *per node* in the
graph. These assert the shape of the fix — the manifests are opened once and
subsequent reads open nothing — rather than a wall-clock number.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.workspace import Workspace
from tests.support.counting_fs import CountingFileSystem


@pytest.fixture
def seeded(tmp_path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="lab")
    experiment = ws.add_project("proj").add_experiment("exp")
    for i in range(3):
        run = experiment.add_run(params={"i": i})
        with run.start() as ctx:
            ctx.artifact.save(f"out-{i}.json", {"value": i})
    return ws


@pytest.fixture
def counted(seeded: Workspace, tmp_path):
    fs = CountingFileSystem(seeded.fs.__class__())
    ws = Workspace(root=tmp_path / "lab", fs=fs)
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: ws
    with TestClient(app) as client:
        yield client, fs


def _manifest_opens(fs: CountingFileSystem) -> int:
    return sum(fs.for_basename("assets.json", m) for m in ("open", "read_text"))


class TestAssetReads:
    def test_asset_ids_resolve_and_warm_reads_open_no_manifest(self, counted) -> None:
        client, fs = counted
        listed = client.get("/api/assets").json()
        assert listed, "fixture produced no assets"
        asset_id = listed[0]["id"]

        fs.reset()
        detail = client.get(f"/api/assets/{asset_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == asset_id
        assert _manifest_opens(fs) == 0, dict(fs.calls)

    def test_unknown_asset_is_404_after_one_revalidation(self, counted) -> None:
        client, fs = counted
        client.get("/api/assets")
        fs.reset()
        assert client.get("/api/assets/does-not-exist").status_code == 404
        # One forced rescan separates "written since the last sweep" from
        # "absent" — never more than one.
        assert _manifest_opens(fs) <= 5, dict(fs.calls)

    def test_lineage_does_not_rescan_per_node(self, counted) -> None:
        client, fs = counted
        asset_id = client.get("/api/assets").json()[0]["id"]
        fs.reset()
        response = client.get(f"/api/assets/{asset_id}/lineage")
        assert response.status_code == 200
        assert _manifest_opens(fs) == 0, dict(fs.calls)

    def test_content_hash_lookup_uses_the_hash_index(self, counted) -> None:
        client, fs = counted
        assets = client.get("/api/assets").json()
        hashed = next((a for a in assets if a.get("content_hash")), None)
        assert hashed is not None, "fixture produced no content-addressed asset"
        target = hashed["content_hash"]
        fs.reset()
        found = client.get("/api/assets", params={"content_hash": target}).json()
        assert [a["id"] for a in found] == [hashed["id"]]
        assert _manifest_opens(fs) == 0, dict(fs.calls)


class TestWorkspaceInfo:
    def test_asset_count_does_not_scan_when_warm(self, counted) -> None:
        client, fs = counted
        first = client.get("/api/workspace/info")
        assert first.status_code == 200
        assert first.json()["assetCount"] >= 1
        fs.reset()
        assert client.get("/api/workspace/info").status_code == 200
        assert _manifest_opens(fs) == 0, dict(fs.calls)
