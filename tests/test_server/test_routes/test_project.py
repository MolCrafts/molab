"""Project asset routes: list, get, versions, and download via payload_path."""

from __future__ import annotations

import shutil
from pathlib import Path

from molab.workspace.history import AgentRef

HELLO = b"hello\n"


def _project_of(exp):
    return exp.project


class TestListProjectAssets:
    def test_lists_an_imported_asset(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("raw", src, action="copy")
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
        asset = project.assets.import_asset("raw", src, action="copy")
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets/{asset.id}")
        assert response.status_code == 200, response.text
        assert response.json()["title"] == "raw"


class TestListProjectAssetVersions:
    def test_origin_kind_per_version(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, run = fresh_run
        project = _project_of(exp)
        with run.start() as ctx:
            path = ctx.get_dir("work") / "hello.txt"
            path.write_bytes(HELLO)
            artifact = ctx.emit_artifact(path, name="hello.txt")
        promoted, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        copied = project.assets.import_asset("raw", src, action="copy")
        with served(ws) as client:
            promoted_body = client.get(f"/api/projects/{project.id}/assets/{promoted.id}/versions")
            copied_body = client.get(f"/api/projects/{project.id}/assets/{copied.id}/versions")
        assert promoted_body.status_code == 200, promoted_body.text
        assert copied_body.status_code == 200, copied_body.text
        assert promoted_body.json()[0]["originKind"] == "artifact"
        assert copied_body.json()[0]["originKind"] == "import"


class TestDownloadProjectAsset:
    def test_promoted_and_copy_return_hello(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, run = fresh_run
        project = _project_of(exp)
        with run.start() as ctx:
            path = ctx.get_dir("work") / "hello.txt"
            path.write_bytes(HELLO)
            artifact = ctx.emit_artifact(path, name="hello.txt")
        promoted, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        copied = project.assets.import_asset("raw", src, action="copy")
        with served(ws) as client:
            promoted_body = client.get(f"/api/projects/{project.id}/assets/{promoted.id}/download")
            copied_body = client.get(f"/api/projects/{project.id}/assets/{copied.id}/download")
        assert promoted_body.status_code == 200, promoted_body.text
        assert promoted_body.content == HELLO
        assert copied_body.status_code == 200, copied_body.text
        assert copied_body.content == HELLO

    def test_directory_payload_is_404(self, served, fresh_run, tmp_path: Path) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        folder = tmp_path / "bundle"
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"ab")
        asset = project.assets.import_asset("bundle", folder, action="copy")
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets/{asset.id}/download")
        assert response.status_code == 404

    def test_unknown_asset_is_404(self, served, fresh_run) -> None:
        ws, exp, _run = fresh_run
        project = _project_of(exp)
        with served(ws) as client:
            response = client.get(f"/api/projects/{project.id}/assets/missing/download")
        assert response.status_code == 404

    def test_duplicated_experiment_is_409(self, served, fresh_run) -> None:
        ws, exp, run = fresh_run
        project = _project_of(exp)
        with run.start() as ctx:
            path = ctx.get_dir("work") / "hello.txt"
            path.write_bytes(HELLO)
            artifact = ctx.emit_artifact(path, name="hello.txt")
        promoted, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        other = ws.add_project("other")
        src = Path(exp.experiment_dir)
        dest = Path(other.project_dir) / "experiments" / src.name
        shutil.copytree(src, dest)
        with served(ws, raise_server_exceptions=False) as client:
            response = client.get(f"/api/projects/{project.id}/assets/{promoted.id}/download")
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert "detail" not in response.json()
        assert error["code"] == "CONFLICT"
        assert len(error["details"]["candidates"]) == 2


class TestLegacyProjectAsset:
    def test_unmigrated_record_is_409_until_rewrite(
        self, served, fresh_run, tmp_path: Path
    ) -> None:
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

        project.assets.rewrite_legacy()
        with served(ws) as client:
            listed = client.get(f"/api/projects/{project.id}/assets")
            downloaded = client.get(f"/api/projects/{project.id}/assets/{LEGACY_ID}/download")
        assert listed.status_code == 200, listed.text
        assert any(item["id"] == LEGACY_ID for item in listed.json())
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == HELLO
