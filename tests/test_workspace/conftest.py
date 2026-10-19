"""Shared fixtures for workspace tests."""

from __future__ import annotations

import pytest

from molab.workspace import Workspace


@pytest.fixture
def workspace(tmp_path):
    return Workspace(root=tmp_path, name="Test Lab")


@pytest.fixture
def project(workspace):
    return workspace.add_project("test-project")


@pytest.fixture
def experiment(project):
    return project.add_experiment(
        "test-experiment",
        params={"lr": 1e-4},
    )


@pytest.fixture
def run(experiment):
    return experiment.add_run(params={"lr": 1e-4})


class StubRunExecutor:
    """A run-executor seam stand-in: canned ``read_outputs`` per execution id.

    ``calls`` logs every ``(run.id, execution_id)`` read. ``execute`` /
    ``aexecute`` are never expected in workspace tests and fail loudly.
    """

    def __init__(self) -> None:
        self.outputs: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []

    def execute(self, run, workflow, **kwargs: object):
        raise AssertionError("workspace tests must not execute through the seam")

    async def aexecute(self, run, workflow, **kwargs: object):
        raise AssertionError("workspace tests must not execute through the seam")

    def read_outputs(self, run, execution_id):
        self.calls.append((run.id, execution_id))
        return dict(self.outputs.get(execution_id, {}))


@pytest.fixture
def stub_executor():
    """Install :class:`StubRunExecutor` on the run-executor seam; restore after."""
    from molab.workspace.run import require_run_executor, set_run_executor

    prev = require_run_executor()
    stub = StubRunExecutor()
    set_run_executor(stub)
    try:
        yield stub
    finally:
        set_run_executor(prev)


@pytest.fixture
def molq_destination(tmp_path, monkeypatch):
    """A real stdio service with an explicitly bound local-files destination."""
    from molq import Molq

    root = tmp_path / "remote"
    root.mkdir()
    with Molq(registry=tmp_path / "molq.db") as client:
        cluster = client.clusters.register(
            name="files", scheduler="shell", target_root=str(tmp_path / "jobs")
        )
        registry = client.rpc("molq.hello")["registry_id"]

        def owned(expected=None):
            if expected is not None and expected != registry:
                raise ValueError("Registry mismatch")
            return client

        monkeypatch.setattr("molab.workspace.connection.get_client", owned)
        yield client, registry, cluster.name, root
