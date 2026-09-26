"""Unit tests for ``molab.workspace.run`` (``Run``).

Logical Run identity and its physical Execution factory.

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the materialize ordering: mkdir -> save the entity JSON ->
record history, so the ``RunDefined`` commit stages an existing ``run.json``
rather than an empty directory. History stays a soft dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.history import GitHistory


def _spy_history(monkeypatch: pytest.MonkeyPatch, entity_file: str) -> list[tuple[str, bool]]:
    """Replace ``GitHistory.record``; log (event, entity JSON exists in paths[0])."""
    seen: list[tuple[str, bool]] = []
    original = GitHistory.record

    def spy(self: GitHistory, event: str, **kwargs: object) -> str | None:
        paths = kwargs.get("paths") or ()
        assert isinstance(paths, tuple)
        exists = bool(paths) and (Path(str(paths[0])) / entity_file).exists()
        seen.append((event, exists))
        return original(self, event, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(GitHistory, "record", spy)
    return seen


class TestRunMaterialize:
    def test_entity_json_exists_when_history_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = Workspace(tmp_path, name="lab")
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        seen = _spy_history(monkeypatch, "run.json")

        experiment.add_run(params={"seed": 1})

        recorded = [exists for event, exists in seen if event == "RunDefined"]
        assert recorded == [True]
