"""The runs / knowledge read-model snapshots (P3-3a).

Two properties carry the whole design and are asserted here rather than
inferred: a rebuild **reuses** unchanged rows (so a poll costs no reads), and
the version bumps **only** when a reader would see something different (so it
is a sound ETag). The parity test against the live-reading path is what keeps
the zero-I/O context assembly from drifting into a different projection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from molexp.workspace import Workspace
from molexp.workspace.read_model import (
    build_knowledge_snapshot,
    build_runs_snapshot,
    rows_changed,
    runs_snapshot_is_stale,
)
from molexp.workspace.run_ops import RunStatus
from molexp.workspace.workspace_context import assemble_workspace_context
from tests.support.counting_fs import CountingFileSystem


@pytest.fixture
def workspace(tmp_path):
    ws = Workspace(root=tmp_path / "lab", name="lab")
    project = ws.add_project("proj")
    experiment = project.add_experiment("exp")
    for i in range(3):
        experiment.add_run(params={"i": i})
    return ws


def _experiment(ws: Workspace):
    return ws.get_project("proj").get_experiment("exp")


class TestBuildRunsSnapshot:
    def test_rows_cover_every_run_newest_first(self, workspace: Workspace) -> None:
        snap = build_runs_snapshot(workspace)
        assert len(snap.rows) == 3
        assert [r.sort_key for r in snap.rows] == sorted(
            (r.sort_key for r in snap.rows), reverse=True
        )
        assert set(snap.by_id) == {r.run_id for r in snap.rows}
        assert snap.by_experiment[("proj", "exp")] == snap.rows

    def test_row_matches_the_wire_row_built_from_the_entity(self, workspace: Workspace) -> None:
        """Parity lock: ``from_row`` and ``from_run`` must agree field for field."""
        from molexp.server.schemas.workspace_runs import WorkspaceRunRow

        snap = build_runs_snapshot(workspace)
        experiment = _experiment(workspace)
        for run in experiment.list_runs():
            from_entity = WorkspaceRunRow.from_run(run, project_name="proj", experiment_name="exp")
            from_snapshot = WorkspaceRunRow.from_row(snap.by_id[run.id])
            assert from_snapshot == from_entity

    def test_stats_count_statuses(self, workspace: Workspace) -> None:
        snap = build_runs_snapshot(workspace)
        assert snap.stats["total"] == 3
        assert snap.stats["pending"] == 3


class TestIncrementalRebuild:
    def test_unchanged_rows_are_reused_by_reference(self, workspace: Workspace) -> None:
        first = build_runs_snapshot(workspace)
        second = build_runs_snapshot(workspace, previous=first)
        assert second.version == first.version
        assert all(a is b for a, b in zip(first.rows, second.rows, strict=True))

    def test_rebuild_reads_nothing_when_unchanged(self, tmp_path) -> None:
        seed = Workspace(root=tmp_path / "lab", name="lab")
        experiment = seed.add_project("p").add_experiment("e")
        for i in range(4):
            experiment.add_run(params={"i": i})

        fs = CountingFileSystem(seed.fs.__class__())
        ws = Workspace(root=tmp_path / "lab", fs=fs)
        first = build_runs_snapshot(ws)
        fs.reset()
        build_runs_snapshot(ws, previous=first)
        assert fs.opens() == 0, dict(fs.calls)

    def test_status_change_bumps_version_and_experiment_version(self, workspace: Workspace) -> None:
        first = build_runs_snapshot(workspace)
        run = _experiment(workspace).list_runs()[0]
        run.update_ops(lambda s: s.model_copy(update={"status": RunStatus.FAILED}))
        second = build_runs_snapshot(workspace, previous=first)
        assert second.version == first.version + 1
        assert second.by_id[run.id].status == "failed"
        assert second.version_for_experiment("proj", "exp") == second.version

    def test_heartbeat_change_does_not_bump_version(self, workspace: Workspace) -> None:
        """A live run re-stamps its heartbeat every 30 s — that must not churn ETags."""
        first = build_runs_snapshot(workspace)
        run = _experiment(workspace).list_runs()[0]
        run.update_ops(
            lambda s: s.model_copy(update={"heartbeat_at": datetime.now(UTC) + timedelta(hours=1)})
        )
        second = build_runs_snapshot(workspace, previous=first)
        assert second.version == first.version

    def test_new_run_is_picked_up(self, workspace: Workspace) -> None:
        first = build_runs_snapshot(workspace)
        _experiment(workspace).add_run(params={"i": 99})
        second = build_runs_snapshot(workspace, previous=first)
        assert len(second.rows) == 4
        assert second.version == first.version + 1

    def test_removed_run_is_evicted(self, workspace: Workspace) -> None:
        import shutil

        first = build_runs_snapshot(workspace)
        experiment = _experiment(workspace)
        victim = experiment.list_runs()[0]
        shutil.rmtree(victim.run_dir)
        second = build_runs_snapshot(workspace, previous=first)
        assert victim.id not in second.by_id
        assert second.version == first.version + 1

    def test_rows_changed_ignores_only_the_heartbeat(self, workspace: Workspace) -> None:
        row = build_runs_snapshot(workspace).rows[0]
        assert not rows_changed(row, row.model_copy(update={"heartbeat_at": datetime.now(UTC)}))
        assert rows_changed(row, row.model_copy(update={"status": "failed"}))


class TestStaleProbe:
    def test_fresh_snapshot_is_not_stale(self, workspace: Workspace) -> None:
        assert not runs_snapshot_is_stale(workspace, build_runs_snapshot(workspace))

    def test_added_run_makes_the_container_stale(self, workspace: Workspace) -> None:
        snap = build_runs_snapshot(workspace)
        _experiment(workspace).add_run(params={"i": 42})
        assert runs_snapshot_is_stale(workspace, snap)


class TestContextFromSnapshots:
    def test_snapshot_assembly_equals_the_reading_assembly(self, workspace: Workspace) -> None:
        now = datetime.now(UTC)
        direct = assemble_workspace_context(workspace, now=now)
        via_snapshots = assemble_workspace_context(
            workspace,
            now=now,
            runs=build_runs_snapshot(workspace),
            assets=_asset_snapshot(workspace),
            knowledge=build_knowledge_snapshot(workspace),
        )
        assert via_snapshots == direct

    def test_snapshot_assembly_does_no_io(self, tmp_path) -> None:
        seed = Workspace(root=tmp_path / "lab", name="lab")
        seed.add_project("p").add_experiment("e").add_run(params={"i": 0})

        fs = CountingFileSystem(seed.fs.__class__())
        ws = Workspace(root=tmp_path / "lab", fs=fs)
        runs = build_runs_snapshot(ws)
        assets = _asset_snapshot(ws)
        knowledge = build_knowledge_snapshot(ws)
        fs.reset()
        assemble_workspace_context(ws, runs=runs, assets=assets, knowledge=knowledge)
        assert fs.total() == 0, dict(fs.calls)


def _asset_snapshot(ws: Workspace):
    from molexp.workspace.assets.scan import build_asset_snapshot

    return build_asset_snapshot(ws.resolve(), fs=ws.fs)


class TestKnowledgeSnapshot:
    def test_scan_is_reused_when_nothing_changed(self, workspace: Workspace) -> None:
        first = build_knowledge_snapshot(workspace)
        second = build_knowledge_snapshot(workspace, previous=first)
        assert second.version == first.version

    def test_new_note_bumps_the_version(self, workspace: Workspace) -> None:
        from molexp.knowledge.concepts import Note

        first = build_knowledge_snapshot(workspace)
        note = Note(workspace.resolve() / "idea")
        note.write_meta()
        note.set_body("# Idea\n\nbody\n")
        second = build_knowledge_snapshot(workspace, previous=first)
        assert second.version == first.version + 1
        assert "idea" in {n.name for n in second.notes}

    def test_backlink_paths_invert_the_index(self, workspace: Workspace) -> None:
        from molexp.knowledge.concepts import Note

        root = workspace.resolve()
        target = Note(root / "target")
        target.write_meta()
        target.set_body("# Target\n")
        source = Note(root / "citing")
        source.write_meta()
        source.set_body("# Source\n\n[see](../target)\n")

        snapshot = build_knowledge_snapshot(workspace)
        assert snapshot.backlink_paths("target") == ["citing"]
        assert snapshot.backlink_paths("citing") == []
