"""Unit tests for ``molab.workspace.experiment`` (``Experiment``).

Experiment entity — one directory per parameter combination.

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the materialize ordering: mkdir -> save the entity JSON ->
record history, so the ``ExperimentCreated`` commit stages an existing ``experiment.json``
rather than an empty directory. History stays a soft dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from molab.workspace import Experiment, GridSpace, Workspace
from molab.workspace.history import GitHistory
from molab.workspace.run import compute_run_definition_hash

_UUID7 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


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


class TestExperimentMaterialize:
    def test_entity_json_exists_when_history_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = Workspace(tmp_path, name="lab").add_project("p")
        seen = _spy_history(monkeypatch, "experiment.json")

        project.add_experiment("e", workflow_source="s.py", params={})

        recorded = [exists for event, exists in seen if event == "ExperimentCreated"]
        assert recorded == [True]


class TestExperimentAddRun:
    """arch-own-02b §4: ``add_run(config_hash=)`` folds it; semantics otherwise frozen."""

    def test_config_hash_reaches_the_definition_hash(self, experiment: Experiment) -> None:
        run = experiment.add_run({"a": 1}, config_hash="sha256:h")

        assert run.metadata.definition_hash == compute_run_definition_hash(
            experiment_revision_id=experiment.metadata.revision_id,
            parameters={"a": 1},
            config_hash="sha256:h",
        )

    def test_same_params_without_id_allocate_two_runs(self, experiment: Experiment) -> None:
        first = experiment.add_run({"a": 1})
        second = experiment.add_run({"a": 1})

        assert first.id != second.id


class TestExperimentEnsureRun:
    """arch-own-02b §4: the one find-by-``definition_hash``-or-create verb."""

    def test_repeat_call_returns_the_same_uuid7_run(self, experiment: Experiment) -> None:
        first = experiment.ensure_run({"a": 1}, config_hash="h")
        second = experiment.ensure_run({"a": 1}, config_hash="h")

        assert first.id == second.id
        assert _UUID7.match(first.id)

    def test_other_config_hash_creates_a_second_run(self, experiment: Experiment) -> None:
        first = experiment.ensure_run({"a": 1}, config_hash="h")
        other = experiment.ensure_run({"a": 1}, config_hash="h2")

        assert other.id != first.id
        assert len(experiment.list_runs()) == 2

    def test_finds_a_run_created_by_add_run(self, experiment: Experiment) -> None:
        added = experiment.add_run({"b": 2})

        found = experiment.ensure_run({"b": 2})

        assert found.id == added.id

    def test_returned_run_is_on_disk(self, experiment: Experiment) -> None:
        run = experiment.ensure_run({"a": 1}, config_hash="h")

        assert experiment.get_run(run.id).id == run.id

    def test_duplicate_definition_resolves_by_record_not_directory_name(
        self, experiment: Experiment
    ) -> None:
        first = experiment.add_run({"a": 1})
        second = experiment.add_run({"a": 1})
        assert first.run_dir.name == "a=1"
        assert second.run_dir.name == "a=1-2"

        # Rename the earlier run's directory so it sorts after the later one.
        first.run_dir.rename(first.run_dir.with_name("a=1-3"))

        found = experiment.ensure_run({"a": 1})

        assert found.id == first.id


class TestExperimentSeedMissingRuns:
    """arch-own-02b §4: seeding goes through ``_ensure_run`` and stays idempotent."""

    def test_repeat_seed_returns_nothing(self, experiment: Experiment) -> None:
        space = GridSpace({"lr": [0.1, 0.2]})

        first = experiment._seed_missing_runs(space)
        second = experiment._seed_missing_runs(space)

        assert len(first) == 2
        assert second == []

    def test_cell_already_ensured_is_not_reseeded(self, experiment: Experiment) -> None:
        existing = experiment.ensure_run({"lr": 0.1})

        seeded = experiment._seed_missing_runs(GridSpace({"lr": [0.1, 0.2]}))

        assert len(seeded) == 1
        assert seeded[0].id != existing.id
        assert seeded[0].metadata.parameters == {"lr": 0.2}
