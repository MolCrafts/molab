"""``params`` is the one spelling for parameter dicts across the factories.

Frozen interface-naming contract (CLAUDE.md): ``Experiment.add_run(params=...)``
and ``Project.add_experiment(params=...)`` share the canonical keyword. It is
the *only* spelling — the former ``parameters=`` alias is gone, so passing it
is a ``TypeError`` rather than a warning.

Explicit-``id`` honouring and slug idempotency of the ``add_*`` factories are
owned by ``test_crud_convergence.py``, not here.
"""

from __future__ import annotations

import pytest

from molexp.workspace import Workspace


@pytest.fixture
def experiment(tmp_path):
    ws = Workspace(root=tmp_path, name="params-unification")
    return ws.add_project("proj").add_experiment("exp")


class TestExperimentAddRun:
    def test_params_keyword_is_canonical(self, experiment):
        run = experiment.add_run(params={"lr": 1e-3})
        assert run.parameters == {"lr": 1e-3}

    def test_parameters_alias_is_gone(self, experiment):
        # The removed alias must fail loudly, not silently create a run whose
        # params were swallowed as an unknown keyword.
        with pytest.raises(TypeError):
            experiment.add_run(parameters={"seed": 7})


class TestProjectAddExperiment:
    def test_params_forwarded_to_parameter_space(self, tmp_path):
        ws = Workspace(root=tmp_path, name="sig")
        exp = ws.add_project("p").add_experiment("e", params={"lr": 1e-4}, n_replicas=2)
        assert exp.params == {"lr": 1e-4}
        assert exp.n_replicas == 2
