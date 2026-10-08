"""Asset preview resolves bytes through find + assets_at, and does not catch ref errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.server.routes.preview import _resolve_dataset_path
from molab.workspace import Workspace
from molab.workspace.errors import RefNotFoundError


class TestPreviewDatasetPath:
    def test_workspace_import_matches_payload_path(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        src = tmp_path / "hello.txt"
        src.write_bytes(b"hello\n")
        asset = ws.data_assets.import_asset("greeting", src, action="copy")
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
        ws.assets.rewrite_legacy()
        assert _resolve_dataset_path(ws, LEGACY_ID) == Path(ws.assets.payload_path(LEGACY_ID))
