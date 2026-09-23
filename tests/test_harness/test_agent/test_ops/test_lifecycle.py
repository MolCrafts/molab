"""The ``harvest_run`` lifecycle tool calls ``molab.knowledge.harvest.harvest_run``.

The tool is the model-facing surface: it never raises, it returns an
``error: <Type>: <message>`` string, and the harvest itself is knowledge's own
function (the workspace ``Run.harvest`` wrapper is not in the path).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from molab.harness.agent.ops import lifecycle as lifecycle_mod
from molab.harness.agent.ops.lifecycle import lifecycle_tools
from molab.knowledge import Finding


class _FakeRun:
    id = "r1"


class _FakeWorkspace:
    """Stand-in for ``molab.workspace.Workspace`` — the scope chain only."""

    def __init__(self, root: object) -> None:
        self.root = root

    def get_project(self, project_id: str) -> _FakeWorkspace:
        return self

    def get_experiment(self, experiment_id: str) -> _FakeWorkspace:
        return self

    def get_run(self, run_id: str) -> _FakeRun:
        return _FakeRun()


class _FakeItem:
    name = "finding-abc"


def _harvest_tool(tmp_path: Path):
    return {t.__name__: t for t in lifecycle_tools(workspace_root=tmp_path)}["harvest_run"]


class TestLifecycleTools:
    def test_harvest_tool_calls_the_knowledge_harvest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[object, type, dict[str, object]]] = []

        def _record(run: object, of: type, **kwargs: object) -> _FakeItem:
            calls.append((run, of, kwargs))
            return _FakeItem()

        monkeypatch.setattr("molab.workspace.Workspace", _FakeWorkspace)
        monkeypatch.setattr("molab.knowledge.harvest.harvest_run", _record)

        result = _harvest_tool(tmp_path)("p", "e", "r1", "narrative")

        assert result == "harvested Finding finding-abc"
        assert len(calls) == 1
        run, of, kwargs = calls[0]
        assert isinstance(run, _FakeRun)
        assert of is Finding
        assert kwargs["narrative"] == "narrative"
        assert kwargs["created_by"] == "agent"

    def test_harvest_tool_maps_a_rejection_to_an_error_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        message = "run r1 is 'pending' — only a terminal run has an outcome to harvest"

        def _explode(run: object, of: type, **kwargs: object) -> _FakeItem:
            raise ValueError(message)

        monkeypatch.setattr("molab.workspace.Workspace", _FakeWorkspace)
        monkeypatch.setattr("molab.knowledge.harvest.harvest_run", _explode)

        result = _harvest_tool(tmp_path)("p", "e", "r1", "narrative")

        assert result == f"error: ValueError: {message}"

    def test_the_workspace_harvest_wrapper_is_not_in_the_path(self) -> None:
        assert "run.harvest(" not in inspect.getsource(lifecycle_mod)
