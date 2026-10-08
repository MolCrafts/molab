"""Unit tests for ``molab.workspace.experiment`` (``Experiment``).

Experiment entity — one directory per parameter combination.

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the materialize ordering: mkdir -> save the entity JSON ->
record history, so the ``ExperimentCreated`` commit stages an existing ``experiment.json``
rather than an empty directory. History stays a soft dependency.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from molab._typing import JSONValue
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

        project.add_experiment("e", params={})

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
            Workspace(tmp_path, name="lab", fs=fs).add_project("p").add_experiment("e", params={})
        )
        for seed in (1, 2, 3):
            experiment.add_run({"seed": seed})
        fs.reset()

        runs = experiment.list_runs()

        assert len(runs) == 3
        assert fs.for_basename("runs", "listdir") == 0, dict(fs.calls)
        assert fs.for_basename("runs", "scandir") == 1, dict(fs.calls)


# arch-own-04a fixtures. Digest is hashlib of the canon, not compute_definition_hash.
D1 = cast(
    dict[str, JSONValue],
    {
        "name": "demo",
        "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
        "links": [],
    },
)
D2 = cast(
    dict[str, JSONValue],
    {
        "name": "demo",
        "task_configs": [
            {"task_id": "prep", "task_type": "demo.prep"},
            {"task_id": "fit", "task_type": "demo.fit"},
        ],
        "links": [{"source": "prep", "target": "fit"}],
    },
)
CODE_CANON = (
    '{"default_target":null,"description":"","n_replicas":1,"name":"code",'
    '"parameter_space":{},"seeds":null,"tags":[],"workflow_document":null}'
)
MOVED_CANON = (
    '{"default_target":null,"description":"","n_replicas":1,"name":"moved",'
    '"parameter_space":{},"seeds":null,"tags":[],"workflow_document":null}'
)
_IR_NAME = "workflow.ir.json"


def _golden(canon: str) -> str:
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _reload(exp: Experiment) -> Experiment:
    """Load from a new workspace so the parent child-cache is not reused."""
    fresh = Workspace(root=exp.workspace.root)
    return fresh.get_project(exp.project.name).get_experiment(exp.name)


def _write_legacy_ir(exp: Experiment, document: dict[str, JSONValue]) -> None:
    """Direct stdlib write. ``workflow_kind`` stays None — not a bind."""
    target = Path(exp.experiment_dir) / _IR_NAME
    target.write_text(json.dumps(document), encoding="utf-8")


def _bind_rejected(exp: Experiment, exc: type[BaseException], call: Callable[[], None]) -> None:
    path = Path(exp.experiment_dir) / "experiment.json"
    before = path.read_bytes()
    with pytest.raises(exc):
        call()
    assert path.read_bytes() == before


def _hash_call_enclosing(path: Path) -> list[str]:
    """Enclosing function of each ``compute_definition_hash`` call, source order."""
    found: list[str] = []

    def walk(node: ast.AST, enclosing: str | None) -> None:
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else None
            if name is None and isinstance(func, ast.Attribute):
                name = func.attr
            if name == "compute_definition_hash":
                found.append(enclosing or "<module>")
        next_enclosing = enclosing
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            next_enclosing = node.name
        for child in ast.iter_child_nodes(node):
            walk(child, next_enclosing)

    walk(ast.parse(path.read_text(encoding="utf-8")), None)
    return found


class TestExperimentBindWorkflow:
    """arch-own-04a ``bind_workflow``. Legacy rows follow arch-own-04d D44.

    A legacy document is a directly written ``workflow.ir.json`` while
    ``workflow_kind`` stays None. ``workflow_source`` is not a parameter.
    """

    def test_bind_document_without_document_raises(self, project) -> None:
        exp = project.add_experiment("e")

        _bind_rejected(exp, ValueError, lambda: exp.bind_workflow("document"))

    def test_bind_document_with_entrypoint_raises(self, project) -> None:
        exp = project.add_experiment("e")

        _bind_rejected(
            exp,
            ValueError,
            lambda: exp.bind_workflow("document", document=D1, entrypoint="a.py:f"),
        )

    def test_bind_rejects_plan_run_id_keyword(self, project) -> None:
        exp = project.add_experiment("e")

        _bind_rejected(
            exp,
            TypeError,
            lambda: exp.bind_workflow("code", plan_run_id="r"),  # type: ignore[call-arg]
        )

    def test_bind_script_raises(self, project) -> None:
        exp = project.add_experiment("e")

        _bind_rejected(exp, ValueError, lambda: exp.bind_workflow("script"))

    def test_bind_non_dict_document_raises(self, project) -> None:
        exp = project.add_experiment("e")
        bad: object = [1]

        _bind_rejected(
            exp,
            TypeError,
            lambda: exp.bind_workflow("code", document=bad),  # type: ignore[arg-type]
        )

    def test_document_bind_persists_ir_and_kind(self, project) -> None:
        exp = project.add_experiment("e")

        exp.bind_workflow("document", document=D1)

        ir_path = Path(exp.experiment_dir) / _IR_NAME
        raw = json.loads((Path(exp.experiment_dir) / "experiment.json").read_text(encoding="utf-8"))
        assert json.loads(ir_path.read_text(encoding="utf-8")) == D1
        assert raw["workflow_kind"] == "document"
        assert raw["workflow_entrypoint"] is None
        assert "workflow_source" not in raw
        reloaded = _reload(exp)
        assert reloaded.workflow_kind == "document"
        assert reloaded.workflow_document == D1

    def test_code_bind_stores_locator_and_snapshot(self, project) -> None:
        exp = project.add_experiment("e")

        exp.bind_workflow("code", entrypoint="train.py:build", document=D1)

        assert exp.metadata.workflow_entrypoint == "train.py:build"
        assert exp.workflow_kind == "code"
        assert exp.workflow_document == D1

    def test_code_rebind_without_document_removes_ir(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("code", entrypoint="train.py:build", document=D1)

        exp.bind_workflow("code", entrypoint="/other/train.py:build")

        assert exp.workflow_document is None
        assert not (Path(exp.experiment_dir) / _IR_NAME).exists()
        assert exp.metadata.workflow_entrypoint == "/other/train.py:build"

    def test_legacy_plan_run_id_survives_code_and_document_binds(self, project) -> None:
        exp = project.add_experiment("e")
        exp.metadata = exp.metadata.model_copy(update={"plan_run_id": "plan-1"})
        exp.save()

        exp.bind_workflow("code", entrypoint="train.py:build", document=D1)
        assert exp.metadata.plan_run_id == "plan-1"
        exp.bind_workflow("document", document=D1)

        assert exp.metadata.plan_run_id == "plan-1"
        assert _reload(exp).metadata.plan_run_id == "plan-1"

    def test_unbound_document_bind_stays_revision_1(self, project) -> None:
        exp = project.add_experiment("e")

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == 1

    def test_same_document_rebind_keeps_revision_id(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("document", document=D1)
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == 1
        assert exp.metadata.revision_id == revision_id

    def test_different_document_bumps_revision(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("document", document=D1)
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("document", document=D2)

        assert exp.metadata.revision == 2
        assert exp.metadata.revision_id != revision_id

    def test_document_to_code_bumps_and_drops_ir(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("document", document=D1)
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("code", entrypoint="train.py:build")

        assert exp.metadata.revision == 2
        assert exp.metadata.revision_id != revision_id
        assert not (Path(exp.experiment_dir) / _IR_NAME).exists()

    def test_code_rebind_keeps_revision(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("code", entrypoint="train.py:build")
        revision = exp.metadata.revision
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("code", entrypoint="/other/train.py:build")

        assert exp.metadata.revision == revision
        assert exp.metadata.revision_id == revision_id
        assert exp.metadata.workflow_entrypoint == "/other/train.py:build"

    def test_code_to_document_bumps_revision(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("code", entrypoint="train.py:build")
        revision = exp.metadata.revision

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == revision + 1

    def test_legacy_ir_to_different_document_bumps(self, project) -> None:
        exp = project.add_experiment("e")
        _write_legacy_ir(exp, D1)
        assert exp.workflow_kind is None

        exp.bind_workflow("document", document=D2)

        assert exp.metadata.revision == 2

    def test_legacy_ir_same_document_keeps_revision_id(self, project) -> None:
        exp = project.add_experiment("e")
        _write_legacy_ir(exp, D1)
        assert exp.workflow_kind is None
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == 1
        assert exp.metadata.revision_id == revision_id

    def test_legacy_code_to_document_bumps_and_clears_entrypoint(self, project) -> None:
        exp = project.add_experiment("e")
        exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": "train.py:build"})
        exp.save()
        assert exp.workflow_kind is None

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == 2
        assert exp.metadata.workflow_entrypoint is None

    def test_legacy_plan_run_id_only_document_bind_is_revision_1(self, project) -> None:
        exp = project.add_experiment("e")
        exp.metadata = exp.metadata.model_copy(update={"plan_run_id": "plan-1"})
        exp.save()
        assert exp.workflow_kind is None
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == 1
        assert exp.metadata.revision_id == revision_id

    def test_document_with_legacy_plan_run_id_rebind_keeps_revision(self, project) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("document", document=D1)
        exp.metadata = exp.metadata.model_copy(update={"plan_run_id": "plan-1"})
        exp.save()
        revision = exp.metadata.revision
        revision_id = exp.metadata.revision_id

        exp.bind_workflow("document", document=D1)

        assert exp.metadata.revision == revision
        assert exp.metadata.revision_id == revision_id

    def test_revising_bind_records_one_experiment_revised(
        self, project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("document", document=D1)
        seen = _spy_history(monkeypatch, "experiment.json")

        exp.bind_workflow("document", document=D2)

        assert [event for event, _exists in seen] == ["ExperimentRevised"]

    def test_same_document_rebind_records_no_revision(
        self, project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exp = project.add_experiment("e")
        exp.bind_workflow("document", document=D1)
        seen = _spy_history(monkeypatch, "experiment.json")

        exp.bind_workflow("document", document=D1)

        assert [event for event, _exists in seen] == []

    def test_unbound_code_hash_matches_code_canon(self, project) -> None:
        exp = project.add_experiment("code")

        assert exp.metadata.definition_hash == _golden(CODE_CANON), CODE_CANON

    def test_code_binds_keep_hash_and_revision_id(self, project) -> None:
        exp = project.add_experiment("code")
        revision_id = exp.metadata.revision_id
        expected = _golden(CODE_CANON)
        assert exp.metadata.definition_hash == expected, CODE_CANON

        exp.bind_workflow("code", entrypoint="train.py:build", document=D1)
        assert exp.metadata.definition_hash == expected, CODE_CANON
        assert exp.metadata.revision == 1
        assert exp.metadata.revision_id == revision_id

        exp.bind_workflow("code", entrypoint="x.py:f")
        assert exp.metadata.definition_hash == expected, CODE_CANON
        assert exp.metadata.revision == 1
        assert exp.metadata.revision_id == revision_id

    def test_same_fields_bound_to_d1_and_d2_hash_differ(self, project) -> None:
        exp = project.add_experiment("doc")
        exp.bind_workflow("document", document=D1)
        first = exp.metadata.definition_hash

        exp.bind_workflow("document", document=D2)

        assert exp.metadata.definition_hash != first

    def test_compute_definition_hash_only_inside_helper(self) -> None:
        root = Path(__file__).resolve().parents[2] / "src" / "molab" / "workspace"

        experiment_sites = _hash_call_enclosing(root / "experiment.py")
        project_sites = _hash_call_enclosing(root / "project.py")

        assert experiment_sites
        assert set(experiment_sites) == {"_experiment_definition_hash"}
        assert project_sites == []

    def test_rename_recomputes_definition_hash(self, project) -> None:
        other = project.workspace.add_project("other")
        exp = project.add_experiment("code")

        exp.move_to(other, new_name="moved")

        expected = "sha256:" + hashlib.sha256(MOVED_CANON.encode("utf-8")).hexdigest()
        assert exp.metadata.name == "moved"
        assert exp.metadata.definition_hash == expected, MOVED_CANON

        fresh = Workspace(root=project.workspace.root).get_project(other.name)
        reloaded = next(item for item in fresh.experiments() if item.name == "moved")
        assert reloaded.metadata.name == "moved"
        assert reloaded.metadata.definition_hash == expected, MOVED_CANON


_IR = {
    "name": "demo",
    "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
    "links": [],
}
_IR2 = {
    "name": "demo2",
    "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
    "links": [],
}


class TestExperiment:
    def test_write_workflow_doc_round_trip(self, tmp_path: Path) -> None:
        exp = Workspace(tmp_path / "ws", name="ws").add_project("p").add_experiment("e")
        exp._write_workflow_doc(_IR)
        path = Path(exp.experiment_dir) / "workflow.ir.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == _IR
        assert "schema_version" not in path.read_text(encoding="utf-8")
        exp._write_workflow_doc(None)
        assert not path.exists()
        exp._write_workflow_doc(None)

    def test_save_does_not_touch_the_document(self, tmp_path: Path) -> None:
        exp = Workspace(tmp_path / "ws", name="ws").add_project("p").add_experiment("e")
        exp.bind_workflow("document", document=_IR)
        path = Path(exp.experiment_dir) / "workflow.ir.json"
        before = path.read_bytes()
        mtime = path.stat().st_mtime_ns
        exp.save()
        assert path.read_bytes() == before
        assert path.stat().st_mtime_ns == mtime
        raw = json.loads((Path(exp.experiment_dir) / "experiment.json").read_text())
        assert "workflow_source" not in raw

    def test_code_rebind_removes_the_document(self, tmp_path: Path) -> None:
        exp = Workspace(tmp_path / "ws", name="ws").add_project("p").add_experiment("e")
        exp.bind_workflow("document", document=_IR)
        exp.bind_workflow("code", entrypoint="a.py:f")
        assert not (Path(exp.experiment_dir) / "workflow.ir.json").exists()

    def test_legacy_experiment_json_is_not_rehydrated(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="ws")
        exp = ws.add_project("p").add_experiment("e")
        path = Path(exp.experiment_dir) / "experiment.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["workflow_source"] = json.dumps(_IR)
        raw["workflow_type"] = "yaml"
        raw["git_commit"] = "abc123"
        path.write_text(json.dumps(raw), encoding="utf-8")
        (Path(exp.experiment_dir) / "workflow.ir.json").unlink(missing_ok=True)
        loaded = Workspace(ws.root).get_project("p").get_experiment("e")
        assert loaded.workflow_document is None
        dumped = loaded.metadata.model_dump()
        assert "workflow_source" not in dumped
        assert "workflow_type" not in dumped
        assert "git_commit" not in dumped
        assert not hasattr(loaded, "workflow_source")

    def test_legacy_workflow_json_is_ignored(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="ws")
        exp = ws.add_project("p").add_experiment("e")
        (Path(exp.experiment_dir) / "workflow.json").write_text(json.dumps(_IR), encoding="utf-8")
        loaded = Workspace(ws.root).get_project("p").get_experiment("e")
        assert loaded.workflow_document is None

    def test_hash_follows_the_document_file(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="ws")
        a = ws.add_project("pa").add_experiment("e", workflow_document=_IR)
        b = ws.add_project("pb").add_experiment("e", workflow_document=_IR2)
        bound = a.metadata.definition_hash
        a = a.project.set_experiment("e", description="x")
        b = b.project.set_experiment("e", description="x")
        assert a.metadata.definition_hash != b.metadata.definition_hash
        a = a.project.set_experiment("e", description="")
        assert a.metadata.definition_hash == bound

    def test_get_run_by_id(self, experiment: Experiment, run: Run) -> None:
        assert experiment.get_run(run.id).id == run.id
        assert "list_runs" not in inspect.getsource(Experiment.get_run)


class TestExperimentAssets:
    def test_returns_the_scope_repository(self, experiment: Experiment) -> None:
        from molab.workspace.artifact_repository import AssetRepository

        assert isinstance(experiment.assets, AssetRepository)
        assert experiment.assets.scope == experiment.scope
