"""Shared fixtures for the knowledge write-verb tests.

The write verbs take a workspace host, so the fixtures here mirror
``tests/test_workspace/conftest.py``: a materialized ``lab`` with one project and
one experiment, plus a ``run`` under that experiment. These tests may import
``molab.workspace`` freely — the layer guard only scans ``src/molab/knowledge/``.
"""

from __future__ import annotations

import pytest

from molab.workspace import Workspace


@pytest.fixture
def lab(tmp_path):
    """A materialized Workspace with one project / experiment (the write hosts)."""
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    workspace.add_project("p").add_experiment("e")
    return workspace


@pytest.fixture
def experiment(lab):
    return lab.get_project("p").get_experiment("e")


@pytest.fixture
def run(experiment):
    return experiment.add_run(params={"seed": 1})
