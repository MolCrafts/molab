"""Params cells and GridSpace → list[Params]."""

from __future__ import annotations

from molab.workspace.param import GridSpace, Params, UniformSpace


class TestParamsClass:
    def test_gridspace_yields_params_cells(self) -> None:
        space = GridSpace({"dp": [10, 25], "n_chains": [20]})
        cells = list(space)
        assert len(cells) == 2
        assert all(isinstance(cell, Params) for cell in cells)
        assert cells[0]["dp"] == 10
        assert dict(cells[1]) == {"dp": 25, "n_chains": 20}

    def test_uniformspace_yields_params(self) -> None:
        space = UniformSpace({"lr": [1e-3, 1e-4]}, n_samples=3, seed=0)
        cells = list(space)
        assert len(cells) == 3
        assert isinstance(cells[0], Params)
        assert "lr" in cells[0]
