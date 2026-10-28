"""The derived ``index:`` block of each ``index.md`` (D89).

After every refresh point inside the owner, a record's reserved keys equal a
fresh :func:`project_index` of the tree. An attempt write refreshes only its
run (a parent row carries no hot state). A refresh keeps any other section
verbatim, and ``set_index_section`` refuses a reserved key.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from molab.workspace import Experiment, Project, Run, Workspace
from molab.workspace.domain import ExecutionStatus
from molab.workspace.entity_record import RESERVED_INDEX_KEYS, read_record
from molab.workspace.folder import Folder
from molab.workspace.fs_local import LocalFileSystem
from molab.workspace.index_projection import project_index, sync_index

_FS = LocalFileSystem()


def _reserved(folder: Folder) -> dict:
    record = read_record(_FS, folder.resolve())
    assert record is not None
    return {key: value for key, value in record.index.items() if key in RESERVED_INDEX_KEYS}


def _in_sync(*folders: Folder) -> None:
    for folder in folders:
        assert _reserved(folder) == project_index(folder), folder.kind


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Workspace, Project, Experiment, Run]:
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    project = ws.add_project("alpha")
    experiment = project.add_experiment("sweep", params={"lr": 1e-3})
    run = experiment.add_run(params={"seed": 0, "v": "ar"})
    return ws, project, experiment, run


class TestShape:
    def test_each_level_carries_its_reserved_keys(self, tree) -> None:
        ws, project, experiment, run = tree

        assert set(_reserved(ws)) == {"children"}
        assert set(_reserved(project)) == {"parent", "children"}
        assert set(_reserved(experiment)) == {"parent", "entrypoint", "scratch", "children"}
        assert set(_reserved(run)) == {"parent", "executions", "latest_status"}

    def test_rows_point_down_and_parents_point_up(self, tree) -> None:
        ws, project, experiment, run = tree

        assert _reserved(ws)["children"] == [
            {
                "name": "alpha",
                "path": "projects/alpha/index.md",
                "id": project.id,
                "description": "",
            }
        ]
        assert _reserved(project)["parent"] == "../../index.md"
        assert _reserved(project)["children"] == [
            {
                "name": "sweep",
                "path": "experiments/sweep/index.md",
                "id": experiment.id,
                "description": "",
                "workflow_kind": None,
                "entrypoint": None,
            }
        ]
        assert _reserved(experiment)["children"] == [
            {
                "name": "seed=0_v=ar",
                "path": "runs/seed=0_v=ar/index.md",
                "id": run.id,
                "params": {"seed": 0, "v": "ar"},
            }
        ]
        assert _reserved(experiment)["scratch"] is False
        assert _reserved(run) == {
            "parent": "../../index.md",
            "executions": [],
            "latest_status": "pending",
        }
        for folder in (project, experiment, run):
            assert (Path(str(folder.resolve())) / _reserved(folder)["parent"]).resolve() == (
                Path(str(folder.parent.resolve())) / "index.md"
            ).resolve()

    def test_rows_are_sorted_by_directory_name(self, tree) -> None:
        _ws, _project, experiment, _run = tree
        experiment.add_run(params={"seed": 9})
        experiment.add_run(params={"seed": 1})

        names = [row["name"] for row in _reserved(experiment)["children"]]

        assert names == sorted(names)


class TestRefreshPoints:
    def test_creation_refreshes_the_new_record_and_its_parent(self, tree) -> None:
        ws, project, experiment, run = tree

        _in_sync(ws, project, experiment, run)

    def test_add_runs_refreshes_the_experiment_once(self, tree, monkeypatch) -> None:
        import molab.workspace.index_projection as projection
        from molab.param import GridSpace

        _ws, _project, experiment, _run = tree
        calls: list[str] = []
        original = projection.refresh_index_at

        def spy(fs, directory, **kwargs: Any):
            calls.append(str(directory))
            return original(fs, directory, **kwargs)

        monkeypatch.setattr(projection, "refresh_index_at", spy)

        runs = experiment.add_runs(GridSpace({"seed": [1, 2, 3]}))

        assert calls.count(str(experiment.resolve())) == 1
        assert len(runs) == 3
        _in_sync(experiment, *runs)

    def test_sweep_seeding_refreshes_the_experiment_once(self, tree, monkeypatch) -> None:
        import molab.workspace.index_projection as projection
        from molab.param import GridSpace

        _ws, _project, experiment, _run = tree
        calls: list[str] = []
        original = projection.refresh_index_at

        def spy(fs, directory, **kwargs: Any):
            calls.append(str(directory))
            return original(fs, directory, **kwargs)

        monkeypatch.setattr(projection, "refresh_index_at", spy)

        experiment._seed_missing_runs(GridSpace({"seed": [4, 5]}))

        assert calls.count(str(experiment.resolve())) == 1
        _in_sync(experiment)

    def test_removal_refreshes_the_parent(self, tree) -> None:
        ws, project, experiment, run = tree
        experiment.del_run(run.id)
        _in_sync(experiment)
        assert _reserved(experiment)["children"] == []

        project.del_experiment(experiment.name)
        _in_sync(project)
        ws.del_project(project.name)
        _in_sync(ws)
        assert _reserved(ws)["children"] == []

    def test_move_refreshes_both_parents_and_the_moved_record(self, tree) -> None:
        ws, project, experiment, _run = tree
        other = ws.add_project("beta")

        experiment.move_to(other, new_name="sweep moved")

        _in_sync(project, other, experiment)
        assert _reserved(project)["children"] == []
        assert [row["name"] for row in _reserved(other)["children"]] == ["sweep moved"]

    def test_a_canonical_change_refreshes_the_parent_row(self, tree) -> None:
        ws, project, experiment, _run = tree
        ws.set_project(project.name, description="melts")
        project.set_experiment(experiment.name, description="sweeps")

        _in_sync(ws, project)
        assert _reserved(ws)["children"][0]["description"] == "melts"
        assert _reserved(project)["children"][0]["description"] == "sweeps"

    def test_bind_workflow_refreshes_the_entrypoint(self, tree, tmp_path) -> None:
        _ws, project, experiment, _run = tree
        script = Path(str(experiment.resolve())) / "workflow.py"
        script.write_text("wf = None\n", encoding="utf-8")

        experiment.bind_workflow("code", entrypoint=f"{script}:wf")
        assert _reserved(experiment)["entrypoint"] == "workflow.py"
        assert _reserved(project)["children"][0]["entrypoint"] == "workflow.py"
        assert _reserved(project)["children"][0]["workflow_kind"] == "code"

        experiment.bind_workflow("document", document={"name": "d", "task_configs": []})
        assert _reserved(experiment)["entrypoint"] == "workflow.ir.json"
        _in_sync(project, experiment)

    def test_an_outside_entrypoint_is_named_as_recorded(self, tree, tmp_path) -> None:
        _ws, _project, experiment, _run = tree
        script = tmp_path / "elsewhere.py"

        experiment.bind_workflow("code", entrypoint=f"{script}:wf")

        assert _reserved(experiment)["entrypoint"] == str(script)

    def test_attempt_writes_refresh_the_run(self, tree) -> None:
        _ws, _project, _experiment, run = tree
        with run.start() as ctx:
            ctx.emit_artifact({"loss": 0.1}, name="metrics.json")
            running = _reserved(run)
            assert running["latest_status"] == "running"
        _in_sync(run)
        rows = _reserved(run)["executions"]
        assert [row["id"] for row in rows] == ["e01"]
        row = rows[0]
        assert row["path"] == "executions/e01"
        assert row["mode"] == "initial"
        assert row["status"] == "succeeded"
        assert row["started_at"] and row["finished_at"]
        assert row["artifacts"] and all(isinstance(p, str) for p in row["artifacts"])
        assert row["error"] is None
        assert _reserved(run)["latest_status"] == "succeeded"

    def test_seal_touches_only_the_run_file(self, tree) -> None:
        _ws, _project, experiment, run = tree
        with run.start() as ctx:
            experiment_index = Path(str(experiment.resolve())) / "index.md"
            before = experiment_index.stat().st_mtime_ns
            run_index = Path(str(run.resolve())) / "index.md"
            run_before = run_index.read_text()
            time.sleep(0.01)

            run._execution_repository().seal(ctx.id, ExecutionStatus.FAILED, error={"type": "Boom"})

            assert experiment_index.stat().st_mtime_ns == before
            assert run_index.read_text() != run_before
            assert _reserved(run)["executions"][0]["error"] == "Boom"
            assert _reserved(run)["latest_status"] == "failed"

    def test_prune_refreshes_the_run(self, tree) -> None:
        _ws, _project, _experiment, run = tree
        with run.start():
            pass
        out = Path(str(run.resolve())) / "executions" / "e01" / "out" / "task"
        out.mkdir(parents=True)
        repo = run._execution_repository()
        repo.mark_pruned("e01", ["out"])

        _in_sync(run)
        assert _reserved(run)["executions"][0]["out"] == ["task"]


class TestSections:
    def test_refresh_keeps_a_non_reserved_section(self, tree) -> None:
        _ws, project, experiment, _run = tree
        rows = [{"path": "knowledges/tg.md", "title": "Tg"}]
        project.set_index_section("notes", rows)

        project.set_experiment(experiment.name, description="refresh me")
        project.add_experiment("second")

        record = read_record(_FS, project.resolve())
        assert record is not None
        assert record.index["notes"] == rows
        _in_sync(project)

    @pytest.mark.parametrize(
        "key", ["parent", "children", "entrypoint", "scratch", "executions", "latest_status"]
    )
    def test_a_reserved_key_is_refused(self, tree, key: str) -> None:
        _ws, project, _experiment, _run = tree

        with pytest.raises(ValueError, match="reserved"):
            project.set_index_section(key, [])

    @pytest.mark.parametrize("key", ["Notes", "1st", "with-dash", ""])
    def test_a_malformed_key_is_refused(self, tree, key: str) -> None:
        _ws, project, _experiment, _run = tree

        with pytest.raises(ValueError):
            project.set_index_section(key, [])


class TestSync:
    def test_sync_rebuilds_every_reserved_key(self, tree) -> None:
        ws, project, experiment, run = tree
        for folder in (ws, project, experiment, run):
            path = Path(str(folder.resolve())) / "index.md"
            text = path.read_text()
            path.write_text(text.replace("index:", "index:\n  stale: kept"))
        record = read_record(_FS, experiment.resolve())
        assert record is not None

        visited = sync_index(ws)

        assert visited == 4
        _in_sync(ws, project, experiment, run)
        stale = read_record(_FS, run.resolve())
        assert stale is not None and stale.index["stale"] == "kept"


class TestFailurePolicy:
    def test_a_failed_refresh_never_fails_the_write(self, tree, monkeypatch) -> None:
        import molab.workspace.index_projection as projection

        _ws, project, _experiment, _run = tree

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(projection, "refresh_index_at", boom)

        project.add_experiment("still-created")

        assert project.has_experiment("still-created")
