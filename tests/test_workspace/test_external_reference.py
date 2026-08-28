"""Index-only external asset pointers — no copy, symlink, or hardlink.

``import_asset(..., action="reference")`` and ``ArtifactAccessor.point``
record an ``external_uri`` in the asset index. The bytes stay where they
already live (e.g. a training ``runs/`` tree outside the molexp workspace).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.workspace import Workspace


def _outside_file(tmp_path: Path, name: str = "payload.bin", data: bytes = b"hello") -> Path:
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    src = foreign / name
    src.write_bytes(data)
    return src


class TestImportAssetReference:
    def test_points_at_source_without_copy_or_link(self, tmp_path: Path) -> None:
        ws_root = tmp_path / "ws"
        ws = Workspace(root=ws_root, name="T")
        src = _outside_file(tmp_path)

        asset = ws.data_assets.import_asset("run-tree", src, action="reference")

        assert asset.import_action == "reference"
        assert asset.external_uri == str(src.resolve())
        assert asset.absolute_path(ws_root) == src.resolve()
        assert asset.absolute_path(ws_root).read_bytes() == b"hello"
        assert asset.content_hash is not None
        assert asset.content_hash.startswith("sha256:")

        record_dir = ws_root / "assets" / asset.asset_id
        assert (record_dir / "asset.json").is_file()
        assert not (record_dir / "payload").exists()
        assert not any(p.is_symlink() for p in record_dir.rglob("*"))
        # Source is untouched and not linked from the workspace tree.
        assert not any(p.is_symlink() for p in ws_root.rglob("*") if p.is_file() or p.is_symlink())
        assert src.exists()

    def test_directory_reference(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        tree = tmp_path / "runs" / "prod-day1"
        tree.mkdir(parents=True)
        (tree / "last.pt").write_bytes(b"ckpt")
        asset = ws.data_assets.import_asset("prod-day1", tree, action="reference")
        assert asset.absolute_path(tmp_path / "ws") == tree.resolve()
        assert (asset.absolute_path(tmp_path / "ws") / "last.pt").read_bytes() == b"ckpt"

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        with pytest.raises(FileNotFoundError):
            ws.data_assets.import_asset("ghost", tmp_path / "nope.bin", action="reference")


class TestArtifactPoint:
    def test_run_artifact_points_outside_without_copy(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        proj = ws.add_project("p")
        exp = proj.add_experiment("e")
        run = exp.add_run()
        src = _outside_file(tmp_path, name="metrics.jsonl", data=b"t=1\n")

        with run.start() as ctx:
            asset = ctx.artifact.point("metrics.jsonl", src)

        assert asset.external_uri == str(src.resolve())
        assert asset.absolute_path(run.run_dir) == src.resolve()
        assert asset.read_bytes(run.run_dir) == b"t=1\n"
        assert not (run.run_dir / "artifacts" / "metrics.jsonl").exists()
        assert not any(p.is_symlink() for p in Path(run.run_dir).rglob("*"))

    def test_checkpoint_point(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        proj = ws.add_project("p")
        exp = proj.add_experiment("e")
        run = exp.add_run()
        src = _outside_file(tmp_path, name="last.pt", data=b"pt")

        with run.start() as ctx:
            asset = ctx.checkpoint.point("last.pt", src)

        assert asset.external_uri == str(src.resolve())
        assert asset.absolute_path(run.run_dir) == src.resolve()
        assert not (run.run_dir / ".ckpt").exists() or not any(
            (run.run_dir / ".ckpt").glob("*.json")
        )
