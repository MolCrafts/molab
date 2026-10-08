"""User-facing CRUD: add / get / set / del + Workspace()/load."""

from __future__ import annotations

import pytest

from molab.workspace import (
    ExperimentNotFoundError,
    ProjectNotFoundError,
    Workspace,
)


class TestWorkspaceCreateLoad:
    def test_create_writes_workspace_json(self, tmp_path) -> None:
        root = tmp_path / "lab"
        ws = Workspace(root, name="Lab")
        ws.materialize()
        assert (root / "workspace.json").is_file()
        assert ws.name == "Lab"

    def test_construct_existing_loads(self, tmp_path) -> None:
        root = tmp_path / "lab"
        Workspace(root, name="Lab").materialize()
        ws2 = Workspace(root, name="Other")
        assert ws2.name == "Lab"

    def test_load_missing_raises(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            Workspace.load(tmp_path / "nope")


class TestProjectExperimentRunCrud:
    def test_noun_get_requires_existing(self, tmp_path) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        with pytest.raises(ProjectNotFoundError):
            ws.project("missing")
        ws.add_project("p")
        with pytest.raises(ExperimentNotFoundError):
            ws.project("p").experiment("missing")

    def test_set_experiment_updates_params(self, tmp_path) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        p = ws.add_project("p")
        p.add_experiment("e", params={"lr": 1e-3}, description="old")
        p.set_experiment("e", params={"lr": 1e-4}, description="new")
        exp = p.experiment("e")
        assert exp.params["lr"] == 1e-4
        assert exp.description == "new"
        # reload
        exp2 = Workspace.load(tmp_path / "lab").project("p").experiment("e")
        assert exp2.params["lr"] == 1e-4
        assert exp2.description == "new"

    def test_set_run_rejects_definition_mutation(self, tmp_path) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        exp = ws.add_project("p").add_experiment("e")
        exp.add_run(params={"epochs": 10}, id="r1")
        with pytest.raises(RuntimeError):
            exp.set_run("r1", params={"epochs": 100})

    def test_del_experiment(self, tmp_path) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        p = ws.add_project("p")
        p.add_experiment("e")
        p.del_experiment("e")
        with pytest.raises(ExperimentNotFoundError):
            p.experiment("e")

    def test_plural_lists(self, tmp_path) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        p = ws.add_project("p")
        p.add_experiment("a")
        p.add_experiment("b")
        assert {e.name for e in p.experiments()} == {"a", "b"}
        assert {x.name for x in ws.projects()} == {"p"}
