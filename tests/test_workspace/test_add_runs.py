"""``Experiment.add_runs`` — materialize a ParamSpace into Runs.

Run-materialization semantics owned here:
- one Run per Cartesian cell, each carrying exactly that cell's params;
- every run gets a fresh UUID id (identity is location, not a function of
  params — ``definition_hash`` supports dedup, never identity);
- ids stay stable across a re-opened Experiment (second-process simulation);
- re-materializing the same space creates fresh runs (a Run is immutable
  intent; there is no idempotent re-add);
- an empty space yields ``[]``.

``derive_run_id``'s own properties are owned by ``test_derive_run_id.py`` —
this file only pins that ``add_runs`` does **not** fold params into identity.
"""

from __future__ import annotations

from molab.workspace import GridSpace, Workspace
from molab.workspace.utils import derive_run_id


def _grid() -> GridSpace:
    return GridSpace({"lr": [1e-4, 5e-4], "batch": [32, 64]})


class TestAddRuns:
    def test_materializes_one_run_per_cell_with_cell_params(self, experiment) -> None:
        expected_cells = [dict(cell) for cell in _grid()]
        runs = experiment.add_runs(_grid())

        assert len(experiment.list_runs()) == len(expected_cells) == 4
        materialized = [dict(r.parameters) for r in runs]
        assert len(materialized) == len(expected_cells)
        for cell in expected_cells:
            assert cell in materialized

    def test_assigns_unique_uuid_ids_not_derived_from_params(self, experiment) -> None:
        runs = experiment.add_runs(_grid())
        ids = {r.id for r in runs}
        assert len(ids) == 4
        for run in runs:
            assert run.id != derive_run_id(dict(run.parameters))

    def test_ids_stable_across_reopened_experiment(self, workspace, tmp_path) -> None:
        project = workspace.add_project("det-project")
        experiment = project.add_experiment("det-exp", params={"lr": 1e-4})
        first_ids = {r.id for r in experiment.add_runs(_grid())}

        # Second process: a fresh Workspace over the same root.
        reopened = Workspace(root=tmp_path).get_project("det-project").get_experiment("det-exp")
        assert {r.id for r in reopened.list_runs()} == first_ids

    def test_repeated_materialization_creates_fresh_runs(self, experiment) -> None:
        experiment.add_runs(_grid())
        experiment.add_runs(_grid())
        assert len(experiment.list_runs()) == 8

    def test_empty_space_returns_empty_list(self, experiment) -> None:
        assert experiment.add_runs(GridSpace({"lr": []})) == []
