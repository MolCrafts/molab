"""Fixtures for the metrics plugin tests: one run in a throwaway workspace."""

from __future__ import annotations

import pytest

from molab.workspace import Workspace


@pytest.fixture
def workspace(tmp_path):
    return Workspace(root=tmp_path, name="Test Lab")


@pytest.fixture
def experiment(workspace):
    project = workspace.add_project("test-project")
    return project.add_experiment(
        "test-experiment",
        params={"lr": 1e-4},
    )


@pytest.fixture
def run(experiment):
    return experiment.add_run(params={"lr": 1e-4})
