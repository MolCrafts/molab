"""``ExecutionContext.register`` copies bytes onto the experiment's assets.

The source may live inside the attempt or outside it. A checkpoint is a file
under ``checkpoints/``, not an asset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.asset_repository import assets_produced_by, content_ref
from molab.workspace.domain import ExecutionOrigin, ImportOrigin


def _outside_file(tmp_path: Path, name: str = "payload.bin", data: bytes = b"hello") -> Path:
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    src = foreign / name
    src.write_bytes(data)
    return src


class TestRegisterSnapshots:
    def test_register_copies_attempt_bytes(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            src = ctx.get_dir("work") / "metrics.jsonl"
            src.write_bytes(b"t=1\n")
            asset = ctx.register(src, title="metrics.jsonl", media_type="application/x-ndjson")
            execution_id = ctx.id
        assert isinstance(asset.origin, ExecutionOrigin)
        assert asset.origin.execution_id == execution_id
        assert asset.ref == f"molab:asset/{asset.id}"
        location = ws.assets_at(asset.scope).payload_path(asset.id)
        assert Path(location).is_file()
        assert content_ref(ws.fs, location) == asset.content
        assert src.read_bytes() == b"t=1\n"
        state = Path(run.run_dir) / "executions" / execution_id / "execution.json"
        assert asset.id not in state.read_text(encoding="utf-8")
        assert not (Path(run.run_dir) / "artifacts").exists()

    def test_register_refuses_a_log_the_solver_wrote(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            direct = ctx.get_dir("out") / "lammps.log"
            direct.write_bytes(b"step 0\n")
            with pytest.raises(ValueError, match="log"):
                ctx.register(direct, title="lammps.log")
            execution_id = ctx.id
        assert direct.read_bytes() == b"step 0\n"
        assert assets_produced_by(ws, execution_id) == []

    def test_register_copies_a_file_outside_the_attempt(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()
        outside = _outside_file(tmp_path, name="metrics.jsonl", data=b"t=1\n")
        with run.start() as ctx:
            asset = ctx.register(outside, title="metrics.jsonl")
        assert outside.read_bytes() == b"t=1\n"
        assert Path(ws.assets_at(asset.scope).payload_path(asset.id)).read_bytes() == b"t=1\n"
        assert isinstance(asset.origin, ExecutionOrigin)
        assert not isinstance(asset.origin, ImportOrigin)

    def test_checkpoint_is_a_path(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()
        with run.start() as ctx:
            path = ctx.checkpoint("last", data={"step": 1})
            execution_id = ctx.id
        assert path == run.execution_dir(execution_id) / "checkpoints" / "last.json"
        assert path.is_file()
        assert assets_produced_by(ws, execution_id) == []
