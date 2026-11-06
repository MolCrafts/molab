"""Project asset routes: list, get, import, and download via payload_path."""

from __future__ import annotations

import shutil
from pathlib import Path

HELLO = b"hello\n"


def _project_of(exp):
    return exp.project


class TestListProjectAssets:
    def test_lists_an_imported_asset(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("raw", src)
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets")
        assert response.status_code == 200, response.text
        body = response.json()
        assert any(item["id"] == asset.id and item["title"] == "raw" for item in body)


class TestGetProjectAsset:
    def test_gets_an_imported_asset(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("raw", src)
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets/{asset.id}")
        assert response.status_code == 200, response.text
        assert response.json()["title"] == "raw"


class TestDownloadProjectAsset:
    def test_imported_asset_returns_hello(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        copied = project.assets.import_asset("raw", src)
        with served(ws) as client:
            copied_body = client.get(f"/api/projects/{project.id}/assets/{copied.id}/download")
        assert copied_body.status_code == 200, copied_body.text
        assert copied_body.content == HELLO
        assert copied.media_type == "text/plain"

    def test_directory_payload_is_404(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        folder = tmp_path / "bundle"
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"ab")
        asset = project.assets.import_asset("bundle", folder)
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets/{asset.id}/download")
        assert response.status_code == 404

    def test_unknown_asset_is_404(self, served, fresh_run) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets/missing/download")
        assert response.status_code == 404

    def test_duplicated_experiment_id_is_not_downloaded(self, served, fresh_run) -> None:
        ws, exp, run = fresh_run
        with run.start() as ctx:
            asset = ctx.register(HELLO, title="hello.txt")
        other = ws.add_project("other")
        src = Path(exp.experiment_dir)
        dest = Path(other.project_dir) / "experiments" / src.name
        shutil.copytree(src, dest)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.get(
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}"
                f"/executions/e01/assets/{asset.id}/content"
            )
        assert response.status_code == 404, response.text
        assert "more than one scope" in response.text


class TestLegacyProjectAsset:
    def test_unmigrated_record_is_409(self, served, fresh_run, tmp_path: Path) -> None:
        from tests.support.legacy_assets import LEGACY_ID, write_legacy_data_asset

        ws, exp, _run = fresh_run
        project = _project_of(exp)
        write_legacy_data_asset(
            Path(project.project_dir),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="project",
            scope_ids=(project.id,),
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
        )
        with served(ws, raise_server_exceptions=False) as client:
            listed = client.get(f"/api/projects/{project.id}/assets")
            got = client.get(f"/api/projects/{project.id}/assets/{LEGACY_ID}")
            downloaded = client.get(f"/api/projects/{project.id}/assets/{LEGACY_ID}/download")
        assert listed.status_code == 409, listed.text
        assert got.status_code == 409, got.text
        assert downloaded.status_code == 409, downloaded.text
        assert listed.json()["error"]["code"] == "MIGRATION_REQUIRED"
        assert got.json()["error"]["code"] == "MIGRATION_REQUIRED"
        assert downloaded.json()["error"]["code"] == "MIGRATION_REQUIRED"
        assert "molab migrate" not in listed.json()["error"]["message"]


def test_asset_download_reads_bounded_ranges(served, fresh_run, tmp_path, monkeypatch):
    ws, exp, run = fresh_run
    project_payload = b"\xff\x00" * 400000
    produced_payload = b"\x00\xff" * 400000
    source = tmp_path / "binary.dat"
    source.write_bytes(project_payload)
    asset = exp.project.assets.import_asset("binary", source)
    with run.start() as ctx:
        produced = ctx.register(produced_payload, title="binary.dat")
    ranges = []
    original = ws.fs.read_range

    def bounded(path, offset, length):
        assert length <= 262144
        ranges.append(length)
        return original(path, offset, length)

    monkeypatch.setattr(type(ws.fs), "read_range", staticmethod(bounded))
    with served(ws) as client:
        urls = [
            (
                f"/api/projects/{exp.project.id}/assets/{asset.id}/download",
                project_payload,
            ),
            (
                f"/api/projects/{exp.project.id}/experiments/{exp.id}/runs/{run.id}"
                f"/executions/e01/assets/{produced.id}/content",
                produced_payload,
            ),
        ]
        for url, payload in urls:
            response = client.get(url)
            assert response.status_code == 200, response.text
            assert response.content == payload
    assert len(ranges) >= 8


class TestImportProjectAsset:
    """``POST /projects/{p}/assets`` — the HTTP twin of ``molab asset import``."""

    def test_registers_a_workspace_file(self, served, tmp_path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        project = ws.add_project("p")
        (tmp_path / "lab" / "pbix-br.pdb").write_text("ATOM\n")
        with served(ws) as client:
            created = client.post(
                f"/api/projects/{project.id}/assets",
                json={"name": "pbix-br", "path": "pbix-br.pdb"},
            )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["title"] == "pbix-br"
        assert body["ref"].startswith("molab:asset/")
        assert body["digest"].startswith("sha256:")
        assert body["file"].endswith("payload.pdb")
        assert body["originKind"] == "import"
        assert body["uri"].endswith("pbix-br.pdb")
        assert "mediaType" in body

    def test_refuses_a_path_outside_the_served_directory(self, served, tmp_path) -> None:
        from molab.workspace import Workspace

        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        project = ws.add_project("p")
        (tmp_path / "outside.txt").write_text("x")
        with served(ws) as client:
            response = client.post(
                f"/api/projects/{project.id}/assets", json={"name": "x", "path": "../outside.txt"}
            )
        assert response.status_code == 422, response.text
