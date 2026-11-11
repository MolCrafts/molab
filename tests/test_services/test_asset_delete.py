"""``services.asset_delete`` — delete one registered asset through molab.

The asset is named by id, ``molab:asset/<id>`` ref, or its workspace-relative
slot directory. A citation (a knowledge document naming the id, or a run that
declares it as an input) refuses the delete. A delete is one history commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.knowledge import Note
from molab.knowledge.write import write_knowledge
from molab.services.asset_delete import AssetCitedError, delete_asset
from molab.services.workspace_check import check_workspace
from molab.workspace import Workspace
from molab.workspace.errors import RefNotFoundError
from molab.workspace.history import GitHistory


def _workspace_with_product(tmp_path: Path) -> tuple[Workspace, str, Path]:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    GitHistory(ws.root).init()
    run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        asset = ctx.register(b"<svg/>\n", title="depiction.svg")
    slot = Path(str(ws.root)) / "projects" / "p" / "experiments" / "e" / "assets"
    (directory,) = [path for path in slot.iterdir() if path.is_dir()]
    return ws, asset.id, directory


def _assert_gone(ws: Workspace, asset_id: str, directory: Path) -> None:
    assert not directory.exists()
    with pytest.raises(RefNotFoundError):
        ws.find(f"molab:asset/{asset_id}")
    assert check_workspace(ws).error_count == 0


class TestDeleteAsset:
    def test_by_id_removes_the_slot_and_records_history(self, tmp_path: Path) -> None:
        ws, asset_id, directory = _workspace_with_product(tmp_path)

        deleted = delete_asset(ws, asset_id)

        assert deleted.asset.id == asset_id
        assert Path(deleted.path) == directory
        _assert_gone(ws, asset_id, directory)
        history = GitHistory(ws.root)
        if history.enabled():
            entry = history.latest(entity_id=asset_id, event="AssetDeleted")
            assert entry is not None

    def test_by_ref(self, tmp_path: Path) -> None:
        ws, asset_id, directory = _workspace_with_product(tmp_path)

        delete_asset(ws, f"molab:asset/{asset_id}")

        _assert_gone(ws, asset_id, directory)

    def test_by_workspace_relative_directory(self, tmp_path: Path) -> None:
        ws, asset_id, directory = _workspace_with_product(tmp_path)
        rel = directory.relative_to(Path(str(ws.root))).as_posix()

        delete_asset(ws, rel)

        _assert_gone(ws, asset_id, directory)

    def test_refuses_when_a_document_cites_it(self, tmp_path: Path) -> None:
        ws, asset_id, directory = _workspace_with_product(tmp_path)
        write_knowledge(
            ws.root,
            name="depictions",
            of=Note,
            created_by="test",
            text=f"![depiction](molab:asset/{asset_id})\n",
        )

        with pytest.raises(AssetCitedError) as caught:
            delete_asset(ws, asset_id)

        assert any("depictions" in citation for citation in caught.value.citations)
        assert "depictions" in str(caught.value)
        assert directory.is_dir()

    def test_refuses_when_a_run_declares_it_as_input(self, tmp_path: Path) -> None:
        ws, asset_id, directory = _workspace_with_product(tmp_path)
        ws.project("p").experiment("e").add_run(params={"seed": 2}, inputs=(asset_id,))

        with pytest.raises(AssetCitedError) as caught:
            delete_asset(ws, asset_id)

        assert any("input" in citation for citation in caught.value.citations)
        assert directory.is_dir()

    def test_unknown_id_raises(self, tmp_path: Path) -> None:
        ws, _asset_id, directory = _workspace_with_product(tmp_path)

        with pytest.raises(RefNotFoundError):
            delete_asset(ws, "0190a0a0-0000-7000-8000-000000000000")
        with pytest.raises(RefNotFoundError):
            delete_asset(ws, "projects/p/experiments/e/assets/no-such-slot")
        assert directory.is_dir()
