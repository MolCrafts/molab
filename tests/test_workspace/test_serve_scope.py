"""Serve-root detection: the opened directory is the application root."""

from __future__ import annotations

import shutil
from pathlib import Path

from molab.workspace import Experiment, Project, Run, Workspace
from molab.workspace.folder import (
    WORKSPACE_EXPERIMENT_KIND,
    WORKSPACE_PROJECT_KIND,
    WORKSPACE_ROOT_KIND,
    WORKSPACE_RUN_KIND,
)
from molab.workspace.scope import descendants, entities, open_serve_root, resolve_in_scope


def _lab(tmp_path: Path) -> tuple[Workspace, Project, Experiment, Run, Project]:
    ws = Workspace(tmp_path / "lab", name="lab")
    alpha = ws.add_project("alpha")
    experiment = alpha.add_experiment("baseline")
    run = experiment.add_run(params={"x": 1})
    beta = ws.add_project("beta")
    return ws, alpha, experiment, run, beta


class TestOpenServeRoot:
    def test_plain_directory_is_a_workspace_and_writes_nothing(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        root = open_serve_root(plain)
        assert root.kind == WORKSPACE_ROOT_KIND
        assert not (plain / "workspace.json").exists()

    def test_each_level_mounts_as_itself(self, tmp_path: Path) -> None:
        ws, project, experiment, run, _beta = _lab(tmp_path)
        opened = {
            ws.root: WORKSPACE_ROOT_KIND,
            project.resolve(): WORKSPACE_PROJECT_KIND,
            experiment.resolve(): WORKSPACE_EXPERIMENT_KIND,
            run.resolve(): WORKSPACE_RUN_KIND,
        }
        for directory, kind in opened.items():
            root = open_serve_root(directory)
            assert root.kind == kind
            assert Path(str(root.resolve())) == Path(str(directory))

    def test_served_project_hides_its_sibling_and_keeps_its_experiment(
        self, tmp_path: Path
    ) -> None:
        _ws, alpha, experiment, _run, beta = _lab(tmp_path)
        root = open_serve_root(alpha.resolve())
        assert [item.id for item in entities(root, Project)] == [alpha.id]
        assert [item.id for item in entities(root, Experiment)] == [experiment.id]
        try:
            resolve_in_scope(root, beta.id)
        except Exception as exc:
            assert type(exc).__name__ == "ProjectNotFoundError"
        else:
            raise AssertionError("sibling project was visible")

    def test_served_experiment_has_no_project_and_ignores_a_parent_id(self, tmp_path: Path) -> None:
        _ws, alpha, experiment, run, _beta = _lab(tmp_path)
        root = open_serve_root(experiment.resolve())
        assert entities(root, Project) == []
        loaded = descendants(root, Run)
        assert [item.id for item in loaded] == [run.id]
        assert loaded[0].ancestor_id(WORKSPACE_PROJECT_KIND) == ""
        assert root.ancestor_id(WORKSPACE_PROJECT_KIND) == ""
        found = resolve_in_scope(root, alpha.id, experiment.id, run.id)
        assert found.id == run.id
        try:
            resolve_in_scope(root, None, "not-this-experiment")
        except Exception as exc:
            assert type(exc).__name__ == "ExperimentNotFoundError"
        else:
            raise AssertionError("sibling experiment was visible")

    def test_parentless_copy_does_not_invent_a_workspace(self, tmp_path: Path) -> None:
        _ws, alpha, experiment, _run, _beta = _lab(tmp_path)
        alone = tmp_path / "alone"
        shutil.copytree(alpha.resolve(), alone)
        assert Workspace.enclosing_root(alone) is None
        root = open_serve_root(alone)
        assert root.kind == WORKSPACE_PROJECT_KIND
        assert root._parent is None
        assert not (alone / "workspace.json").exists()
        assert [item.name for item in entities(root, Experiment)] == [experiment.name]

    def test_workspace_still_sees_every_project(self, tmp_path: Path) -> None:
        ws, alpha, _experiment, _run, beta = _lab(tmp_path)
        root = open_serve_root(ws.root)
        assert {item.id for item in entities(root, Project)} == {alpha.id, beta.id}
