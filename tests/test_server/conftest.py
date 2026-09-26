"""Shared server-route fixtures: a served workspace and terminal runs.

``served`` binds the app to one workspace through
``set_workspace_path_override`` and always resets it on teardown, so a test
that fails mid-request can no longer leak its workspace into the next test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.workspace import Experiment, Run, Workspace

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]
IrDocument = dict[str, object]

ECHO_TASK_TYPE = "arch_own_echo"


@pytest.fixture
def served() -> Iterator[ServedFactory]:
    """Factory: ``served(ws, *, raise_server_exceptions=True) -> TestClient``.

    The returned client is not yet entered; use it as ``with client: ...`` so
    the app lifespan runs. The workspace override is reset after the test.
    """

    def _serve(ws: Workspace, *, raise_server_exceptions: bool = True) -> TestClient:
        set_workspace_path_override(Path(str(ws.root)))
        app = create_app(serve_static=False)
        return TestClient(app, raise_server_exceptions=raise_server_exceptions)

    try:
        yield _serve
    finally:
        set_workspace_path_override(None)


def _fresh_run(tmp_path: Path) -> RunFixture:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"x": 1})
    return ws, exp, run


@pytest.fixture
def fresh_run(tmp_path: Path) -> RunFixture:
    """A run with no attempt yet (``run.executions == []``)."""
    return _fresh_run(tmp_path)


@pytest.fixture
def terminal_run(tmp_path: Path) -> RunFixture:
    """A run whose only attempt ``e01`` is sealed ``succeeded``."""
    ws, exp, run = _fresh_run(tmp_path)
    with run.start() as ctx:
        ctx.mark_succeeded()
    return ws, exp, run


@pytest.fixture
def failed_run(tmp_path: Path) -> RunFixture:
    """A run whose only attempt ``e01`` is sealed ``failed``."""
    ws, exp, run = _fresh_run(tmp_path)
    with run.start() as ctx:
        ctx.mark_failed("unique-oom-marker")
    return ws, exp, run


class _Echo:
    """Task body for the ``arch_own_echo`` IR task type."""

    def __init__(self, config: dict[str, object]) -> None:
        self._task_config = dict(config)

    async def execute(self, ctx: object) -> dict[str, bool]:
        return {"ok": True}


def _echo_factory(config: dict[str, object]) -> _Echo:
    return _Echo(config)


@pytest.fixture
def echo_document() -> IrDocument:
    """A one-task UI-authored IR document whose task type is registered.

    Registers ``arch_own_echo`` on the default registry only when absent (the
    registry is process-global), then returns the IR the canvas would PUT.
    """
    from molab.workflow.registry import default_registry

    if not default_registry.has(ECHO_TASK_TYPE):
        default_registry.register(ECHO_TASK_TYPE, _echo_factory)
    return {
        "name": "ui-doc",
        "task_configs": [{"task_id": "echo", "task_type": ECHO_TASK_TYPE, "config": {}}],
        "links": [],
        "metadata": {},
    }
