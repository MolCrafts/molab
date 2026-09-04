"""Tests for ``molexp.workspace.curation.reorg`` reorganization helpers.

Pins ``move_run`` (relocate a Run to another Experiment, plus the
destination-collision guard that propagates ``FolderMoveCollisionError``
rather than swallowing it), ``move_experiment`` (including across workspace
roots), ``strip_legacy_ops``, ``rehome_asset`` (re-import a DataAsset payload
into another scope, preserving its content hash) and ``delete_folder``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molexp.ids import generate_uuid7
from molexp.workspace import FolderMoveCollisionError, Workspace
from molexp.workspace.curation import (
    delete_folder,
    move_experiment,
    move_run,
    rehome_asset,
    strip_legacy_ops,
)


class TestMoveRun:
    def test_run_relocates_to_target_experiment(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Reorg Lab")
        proj = ws.add_project("proj")
        source_exp = proj.add_experiment("source-exp", params={})
        target_exp = proj.add_experiment("target-exp", params={})
        run = source_exp.add_run(params={"seed": 0})
        old_dir = Path(str(run.run_dir))
        assert old_dir.exists()

        move_run(run, target_exp)

        assert run.id in [r.id for r in target_exp.list_runs()]
        assert run.id not in [r.id for r in source_exp.list_runs()]
        assert not old_dir.exists()

    def test_collision_propagates(self, tmp_path: Path) -> None:
        # The target already holds a run at the same id; the underlying move_to
        # must refuse rather than clobber — the typed collision error propagates.
        ws = Workspace(root=tmp_path / "lab", name="Collision Lab")
        proj = ws.add_project("proj")
        source_exp = proj.add_experiment("source-exp", params={})
        target_exp = proj.add_experiment("target-exp", params={})
        shared_id = generate_uuid7()
        run = source_exp.add_run(params={"seed": 0}, id=shared_id)
        target_exp.add_run(params={"seed": 1}, id=shared_id)

        with pytest.raises(FolderMoveCollisionError):
            move_run(run, target_exp)


class TestMoveExperiment:
    def test_experiment_relocates_to_target_project(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Reorg Lab")
        source_proj = ws.add_project("source-proj")
        target_proj = ws.add_project("target-proj")
        exp = source_proj.add_experiment("cell", params={})
        run = exp.add_run(params={"seed": 0})
        old_dir = Path(str(exp.experiment_dir))
        run_id = run.id

        move_experiment(exp, target_proj)

        assert exp.id in [e.id for e in target_proj.list_experiments()]
        assert exp.id not in [e.id for e in source_proj.list_experiments()]
        assert not old_dir.exists()
        moved = target_proj.get_experiment(exp.id)
        assert run_id in [r.id for r in moved.list_runs()]

    def test_cross_workspace_keeps_id_and_runs(self, tmp_path: Path) -> None:
        src_ws = Workspace(root=tmp_path / "lab-v2", name="lab-v2")
        dst_ws = Workspace(root=tmp_path / "lab", name="lab")
        src_proj = src_ws.add_project("peo-tg")
        dst_proj = dst_ws.add_project("peo-tg")
        exp = src_proj.add_experiment("ff-regression", params={})
        run = exp.add_run(params={"dp": 25})
        exp_id, run_id = exp.id, run.id
        old_dir = Path(str(exp.experiment_dir))

        move_experiment(exp, dst_proj)

        assert not old_dir.exists()
        assert exp_id not in [e.id for e in src_proj.list_experiments()]
        moved = dst_ws.project("peo-tg").get_experiment(exp_id)
        assert moved.name == "ff-regression"
        assert run_id in [r.id for r in moved.list_runs()]
        assert Path(str(moved.experiment_dir)).is_relative_to(dst_ws.root)


class TestStripLegacyOps:
    def test_removes_ops_sidecar_and_counts(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Ops Lab")
        run = ws.add_project("p").add_experiment("e", params={}).add_run(params={})
        ops = Path(str(run.run_dir)) / "ops"
        ops.mkdir()
        (ops / "run.json").write_text("{}")

        assert strip_legacy_ops(run) == 1
        assert not ops.exists()
        assert strip_legacy_ops(run) == 0

    def test_walks_workspace(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Ops Lab")
        exp = ws.add_project("p").add_experiment("e", params={})
        a = exp.add_run(params={"i": 1})
        b = exp.add_run(params={"i": 2})
        (Path(str(a.run_dir)) / "ops").mkdir()
        (Path(str(b.run_dir)) / "ops").mkdir()

        assert strip_legacy_ops(ws) == 2


class TestRehomeAsset:
    def test_content_hash_preserved_on_reimport(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Rehome Lab")
        target = ws.add_project("dest")

        payload_src = tmp_path / "payload"
        payload_src.mkdir()
        (payload_src / "data.bin").write_text("payload-bytes")
        asset = ws.data_assets.import_asset("dataset", payload_src, action="copy")
        original_hash = asset.content_hash
        assert original_hash is not None
        assert original_hash.startswith("sha256:")

        rehomed = rehome_asset(asset, source=ws, target=target, action="copy")
        assert rehomed.content_hash == original_hash
        assert rehomed.name == asset.name


class TestDeleteFolder:
    def test_removes_folder_and_drops_from_listing(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Delete Lab")
        proj = ws.add_project("doomed")
        proj_dir = Path(str(proj.project_dir))
        assert proj_dir.exists()

        delete_folder(proj)

        assert not proj_dir.exists()
        assert proj.id not in [p.id for p in ws.list_projects()]
