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

from molab.workspace import Experiment, GridSpace, Run, Workspace
from molab.workspace.fs_local import LocalFileSystem
from molab.workspace.history import GitHistory
from molab.workspace.run import compute_run_definition_hash
from tests.support.counting_fs import CountingFileSystem

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


class TestExperimentFindRun:
    """arch-own-02c §0: ``find_run`` is a read-only ``definition_hash`` lookup."""

    def test_empty_experiment_finds_nothing(self, experiment: Experiment) -> None:
        assert experiment.find_run({"a": 1}) is None

    def test_finds_the_ensured_run_by_config_hash(self, experiment: Experiment) -> None:
        ensured = experiment.ensure_run({"a": 1}, config_hash="h")

        found = experiment.find_run({"a": 1}, config_hash="h")

        assert found is not None
        assert found.id == ensured.id

    def test_missing_config_hash_is_a_different_definition(self, experiment: Experiment) -> None:
        experiment.ensure_run({"a": 1}, config_hash="h")

        assert experiment.find_run({"a": 1}) is None

    def test_other_config_hash_is_a_different_definition(self, experiment: Experiment) -> None:
        experiment.ensure_run({"a": 1}, config_hash="h")

        assert experiment.find_run({"a": 1}, config_hash="h2") is None

    def test_never_creates(self, experiment: Experiment) -> None:
        assert experiment.find_run({"a": 1}) is None
        assert len(experiment.list_runs()) == 0

        experiment.ensure_run({"a": 1}, config_hash="h")
        before = len(experiment.list_runs())

        experiment.find_run({"a": 1}, config_hash="h")
        experiment.find_run({"a": 1})
        experiment.find_run({"a": 1}, config_hash="h2")

        assert len(experiment.list_runs()) == before == 1

    def test_finds_a_run_created_by_add_run(self, experiment: Experiment) -> None:
        added = experiment.add_run({"b": 2})

        found = experiment.find_run({"b": 2})

        assert found is not None
        assert found.id == added.id

    def test_one_index_for_find_and_ensure(
        self, experiment: Experiment, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = Experiment._definition_index
        calls: list[int] = []

        def counting(self: Experiment) -> dict[str, Run]:
            calls.append(1)
            return original(self)

        monkeypatch.setattr(Experiment, "_definition_index", counting)

        experiment.find_run({"a": 1})
        assert len(calls) == 1

        experiment.ensure_run({"a": 1})
        assert len(calls) == 2


class TestExperimentListRuns:
    """arch-own-02b review handoff: the runs container is walked with ``scandir``."""

    def test_list_runs_uses_scandir_not_listdir(self, tmp_path: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        experiment = (
            Workspace(tmp_path, name="lab", fs=fs)
            .add_project("p")
            .add_experiment("e", workflow_source="s.py", params={})
        )
        for seed in (1, 2, 3):
            experiment.add_run({"seed": seed})
        fs.reset()

        runs = experiment.list_runs()

        assert len(runs) == 3
        assert fs.for_basename("runs", "listdir") == 0, dict(fs.calls)
        assert fs.for_basename("runs", "scandir") == 1, dict(fs.calls)
