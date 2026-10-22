"""Emitted artifacts are content-addressed snapshots inside the attempt.

``ExecutionContext.emit_artifact`` requires the source to already live inside
the execution workdir. A reference import is an ``ImportOrigin`` with
``location is None``; it is not an index row and it stores no ``external_uri``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.artifact_repository import content_ref


def _outside_file(tmp_path: Path, name: str = "payload.bin", data: bytes = b"hello") -> Path:
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    src = foreign / name
    src.write_bytes(data)
    return src


class TestEmitArtifactSnapshots:
    def test_run_artifact_snapshots_workdir_bytes_into_cas(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "ws", name="T")
        proj = ws.add_project("p")
        exp = proj.add_experiment("e")
        run = exp.add_run()

        with run.start() as ctx:
            src = ctx.get_dir("work") / "metrics.jsonl"
            src.write_bytes(b"t=1\n")
            artifact = ctx.emit_artifact(
                src, name="metrics.jsonl", media_type="application/x-ndjson"
            )

        # The product is promoted out of scratch into ``artifacts/`` and
        # hashed in place — no content-addressed side copy, no symlink. Its
        # ``source_path`` records the tier it actually came from.
        assert artifact.source_path == "work/metrics.jsonl"
        assert artifact.path == "artifacts/metrics.jsonl"
        assert not artifact.path.startswith("/")
        location = run.artifact_location(artifact.execution_id, artifact)
        assert Path(location).is_file()
        assert content_ref(ws.fs, location) == artifact.content

        state = Path(run.run_dir) / "executions" / artifact.execution_id / "execution.json"
        assert artifact.id in state.read_text()
        assert not (Path(run.run_dir) / "artifacts").exists()
        assert not any(p.is_symlink() for p in Path(run.run_dir).rglob("*"))

    def test_emit_artifact_accepts_a_log_the_solver_wrote_into_the_attempt(
        self, tmp_path: Path
    ) -> None:
        """A solver told to log straight into the attempt's own directory still
        produces a registerable Artifact — the file belongs to this Execution,
        which is the only thing emit_artifact needs to be true."""
        ws = Workspace(root=tmp_path / "ws", name="T")
        run = ws.add_project("p").add_experiment("e").add_run()

        with run.start() as ctx:
            direct = ctx.get_dir("out") / "lammps.log"
            direct.write_bytes(b"step 0\n")
            artifact = ctx.emit_artifact(direct, name="lammps.log")

        # Promotion works the same from every tier: the raw log stays where
        # the solver put it and a registered copy lands in ``artifacts/``.
        assert artifact.source_path == "out/lammps.log"
        assert artifact.path == "artifacts/lammps.log"
        assert (
            content_ref(ws.fs, run.artifact_location(artifact.execution_id, artifact))
            == artifact.content
        )
        assert [a.name for a in run.executions[-1].artifacts] == ["lammps.log"]

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
        # Checkpoints have their own declared directory — they are not a
        # subdirectory of scratch, and ``source_path`` says so.
        assert artifact.source_path == "checkpoints/last.json"
        assert artifact.content.digest.startswith("sha256:")
        assert (
            content_ref(ws.fs, run.artifact_location(artifact.execution_id, artifact))
            == artifact.content
        )
        assert not any(p.is_symlink() for p in Path(run.run_dir).rglob("*"))
