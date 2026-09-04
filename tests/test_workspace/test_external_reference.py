"""Index-only external asset pointers — no copy, symlink, or hardlink.

``import_asset(..., action="reference")`` records an ``external_uri`` in the
asset index. The bytes stay where they already live (e.g. a training
``runs/`` tree outside the molexp workspace).

Run-produced outputs no longer support external pointers: schema v2 snapshots
them through :meth:`ExecutionContext.emit_artifact`, which requires the source
to already live inside the execution workdir and content-addresses the bytes
(no symlink / hardlink, no external pointer). Those invariants are locked here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.workspace import Workspace
from molexp.workspace.content_store import ContentStore


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


class TestEmitArtifactSnapshots:
    def test_run_artifact_snapshots_workdir_bytes_into_cas(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        proj = ws.add_project("p")
        exp = proj.add_experiment("e")
        run = exp.add_run()

        with run.start() as ctx:
            src = ctx.workdir / "metrics.jsonl"
            src.write_bytes(b"t=1\n")
            artifact = ctx.emit_artifact(
                src, name="metrics.jsonl", media_type="application/x-ndjson"
            )

        # Content is addressed, not copied into ``artifacts/`` or linked.
        assert artifact.source_path == "work/metrics.jsonl"
        assert not artifact.source_path.startswith("/")
        assert ContentStore(ws.root, fs=ws.fs).verify(artifact.content)

        record = (
            Path(run.run_dir)
            / "executions"
            / artifact.execution_id
            / "artifacts"
            / artifact.id
            / "artifact.json"
        )
        assert record.is_file()
        assert not (Path(run.run_dir) / "artifacts" / "metrics.jsonl").exists()
        assert not any(p.is_symlink() for p in Path(run.run_dir).rglob("*"))

    def test_emit_artifact_rejects_source_outside_workdir(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()
        outside = _outside_file(tmp_path, name="metrics.jsonl", data=b"t=1\n")

        with run.start() as ctx, pytest.raises(ValueError):
            ctx.emit_artifact(outside, name="metrics.jsonl")

    def test_checkpoint_emits_semantically_typed_artifact(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()

        with run.start() as ctx:
            artifact = ctx.checkpoint("last", data={"step": 1})

        assert artifact.semantic_type == "checkpoint"
        assert artifact.source_path == "work/checkpoints/last.json"
        assert artifact.content.digest.startswith("sha256:")
        assert ContentStore(ws.root, fs=ws.fs).verify(artifact.content)
        assert not any(p.is_symlink() for p in Path(run.run_dir).rglob("*"))
