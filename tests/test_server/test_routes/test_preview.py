"""Asset preview resolves bytes through find + assets_at, and does not catch ref errors."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from molab.server.routes.preview import _resolve_dataset_path
from molab.workspace import Workspace
from molab.workspace.errors import RefNotFoundError


class TestPreviewDatasetPath:
    def test_workspace_import_matches_payload_path(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        src = tmp_path / "hello.txt"
        src.write_bytes(b"hello\n")
        asset = ws.assets.import_asset("greeting", src)
        assert _resolve_dataset_path(ws, asset.id) == Path(ws.assets.payload_path(asset.id))

    def test_unknown_id_raises_ref_not_found(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        with pytest.raises(RefNotFoundError) as exc_info:
            _resolve_dataset_path(ws, "nope")
        assert exc_info.value.segment == "asset"

    def test_unknown_preview_is_404(self, served, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        with served(ws, raise_server_exceptions=False) as client:
            response = client.get("/api/assets/nope/preview")
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_unmigrated_legacy_preview_is_409(self, served, tmp_path: Path) -> None:
        from tests.support.legacy_assets import HELLO, LEGACY_ID, write_legacy_data_asset

        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
        )
        with served(ws, raise_server_exceptions=False) as client:
            response = client.get(f"/api/assets/{LEGACY_ID}/preview")
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "MIGRATION_REQUIRED"
        assert "molab migrate" not in response.json()["error"]["message"]


class TestCanonicalAssetRoutes:
    def test_workspace_import_metadata_and_bytes(self, served, fresh_run, tmp_path: Path) -> None:
        workspace, _, _ = fresh_run
        source = tmp_path / "workspace-data.txt"
        source.write_bytes(b"workspace evidence\n")
        asset = workspace.assets.import_asset("workspace source", source)
        with served(workspace) as client:
            response = client.get(f"/api/assets/{asset.id}")
            downloaded = client.get(f"/api/assets/{asset.id}/download")
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["id"] == asset.id
        assert record["ref"] == f"molab:asset/{asset.id}"
        assert record["projectId"] is None
        assert record["originKind"] == "import"
        assert record["uri"].endswith("workspace-data.txt")
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == source.read_bytes()
        assert downloaded.headers["content-type"].startswith("text/plain")

    def test_experiment_produced_asset_preserves_origin_and_bytes(self, served, fresh_run) -> None:
        workspace, experiment, run = fresh_run
        with run.start() as context:
            asset = context.register(b"run evidence\n", title="evidence.txt")
        with served(workspace) as client:
            response = client.get(f"/api/assets/{asset.id}")
            downloaded = client.get(f"/api/assets/{asset.id}/download")
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["projectId"] == experiment.project.id
        assert record["originProjectId"] == experiment.project.id
        assert record["originExperimentId"] == experiment.id
        assert record["runId"] == run.id
        assert record["executionId"] == context.id
        assert record["originKind"] == "execution"
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"run evidence\n"

    def test_experiment_serve_boundary_hides_workspace_and_sibling_assets(
        self, served, fresh_run, tmp_path: Path
    ) -> None:
        workspace, experiment, _ = fresh_run
        source = tmp_path / "private.txt"
        source.write_bytes(b"private workspace evidence\n")
        root_asset = workspace.assets.import_asset("root private", source)
        sibling = experiment.project.add_experiment("private-sibling")
        source.write_bytes(b"private sibling evidence\n")
        sibling_asset = sibling.assets.import_asset("sibling private", source)
        with served(SimpleNamespace(root=experiment.experiment_dir)) as client:
            for asset in (root_asset, sibling_asset):
                for suffix in ("", "/download"):
                    response = client.get(f"/api/assets/{asset.id}{suffix}")
                    assert response.status_code == 404, response.text
                    assert response.json()["error"]["code"] == "NOT_FOUND"

    @pytest.mark.parametrize("state", ["missing", "changed", "directory"])
    def test_unavailable_or_directory_payload_is_404(
        self, served, fresh_run, tmp_path: Path, state: str
    ) -> None:
        workspace, experiment, _ = fresh_run
        source = tmp_path / "source.txt"
        source.write_bytes(b"original bytes\n")
        asset = experiment.assets.import_asset("evidence", source)
        payload = Path(experiment.assets.payload_path(asset.id))
        if state == "missing":
            payload.unlink()
        elif state == "changed":
            payload.write_bytes(b"different bytes\n")
        else:
            directory = tmp_path / "bundle"
            directory.mkdir()
            (directory / "one.txt").write_bytes(b"one\n")
            asset = experiment.assets.import_asset("bundle", directory)
        with served(workspace) as client:
            response = client.get(f"/api/assets/{asset.id}/download")
        assert response.status_code == 404, response.text

    @pytest.mark.parametrize("suffix", ["", "/download"])
    def test_unknown_id_is_404(self, served, fresh_run, suffix: str) -> None:
        workspace, _, _ = fresh_run
        with served(workspace) as client:
            response = client.get(f"/api/assets/unknown{suffix}")
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_download_streams_bounded_filesystem_ranges(
        self, served, fresh_run, tmp_path: Path, monkeypatch
    ) -> None:
        workspace, experiment, _ = fresh_run
        source = tmp_path / "binary.dat"
        content = b"\x00\xff" * 400000
        source.write_bytes(content)
        asset = experiment.assets.import_asset("binary", source)
        reads = []
        read_range = workspace.fs.read_range

        def bounded(path, offset, length):
            assert length <= 262144
            reads.append(length)
            return read_range(path, offset, length)

        monkeypatch.setattr(type(workspace.fs), "read_range", staticmethod(bounded))
        with served(workspace) as client:
            response = client.get(f"/api/assets/{asset.id}/download")
        assert response.status_code == 200, response.text
        assert response.content == content
        assert len(reads) >= 4
