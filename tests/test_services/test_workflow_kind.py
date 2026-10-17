"""Legacy workflow-kind classification."""

from __future__ import annotations

import json
from pathlib import Path

from molab._typing import JSONValue
from molab.services.workflow_kind import (
    classify_legacy_workflow,
    needs_workflow_kind_migration,
)
from molab.workspace import Experiment, Workspace

DOC_A: dict[str, JSONValue] = {
    "workflow_id": "workflow_00000000",
    "name": "constant_add",
    "task_configs": [
        {
            "task_id": "a",
            "task_type": "core.constant",
            "config": {"value": 2},
            "status": "pending",
        },
        {
            "task_id": "b",
            "task_type": "core.constant",
            "config": {"value": 3},
            "status": "pending",
        },
        {
            "task_id": "c",
            "task_type": "core.add",
            "config": {},
            "status": "pending",
        },
    ],
    "links": [
        {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
        {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
    ],
    "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
}

GRAPH_IR: dict[str, JSONValue] = {
    "name": "g",
    "tasks": [{"task_id": "t", "task_type": "core.constant"}],
    "edges": [],
}

_ENTRYPOINT = "wf.py:build"


def _experiment(tmp_path: Path, name: str) -> Experiment:
    workspace = Workspace(tmp_path / "lab", name="lab")
    project = workspace.add_project("proj")
    return project.add_experiment(name)


def _reload(exp: Experiment) -> Experiment:
    workspace = Workspace(Path(str(exp.workspace.root)), name="lab")
    return workspace.get_project("proj").get_experiment(exp.name)


def _set_metadata(exp: Experiment, **updates: str) -> None:
    exp.metadata = exp.metadata.model_copy(update=updates)
    exp.save()


def _write_ir(exp: Experiment, document: dict[str, JSONValue]) -> None:
    path = Path(exp.experiment_dir) / "workflow.ir.json"
    path.write_text(json.dumps(document), encoding="utf-8")


def _stamp_workflow_source(exp: Experiment, source: str) -> Experiment:
    path = Path(exp.experiment_dir) / "experiment.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["workflow_source"] = source
    path.write_text(json.dumps(payload), encoding="utf-8")
    return _reload(exp)


class TestClassifyLegacyWorkflow:
    def test_entrypoint_and_graph_ir_is_code(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "entry-graph")
        _set_metadata(exp, workflow_entrypoint=_ENTRYPOINT)
        _write_ir(exp, GRAPH_IR)

        found = classify_legacy_workflow(exp)

        assert found.kind == "code"
        assert found.entrypoint == _ENTRYPOINT
        assert found.document == GRAPH_IR
        assert found.note is None

    def test_entrypoint_and_plan_run_id_is_code(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "entry-plan")
        _set_metadata(exp, workflow_entrypoint=_ENTRYPOINT, plan_run_id="p1")

        found = classify_legacy_workflow(exp)

        assert found.kind == "code"

    def test_plan_run_id_only_stays_unbound(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "plan")
        _set_metadata(exp, plan_run_id="p1")

        found = classify_legacy_workflow(exp)

        assert found.kind is None
        assert found.note is not None
        assert "legacy plan run" in found.note

    def test_document_file_only_is_document(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "document")
        _write_ir(exp, DOC_A)

        found = classify_legacy_workflow(exp)

        assert found.kind == "document"
        assert found.document == DOC_A

    def test_graph_ir_without_locator_is_memo_only_code(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "memo")
        _write_ir(exp, GRAPH_IR)

        found = classify_legacy_workflow(exp)

        assert found.kind == "code"
        assert found.entrypoint is None
        assert found.note is not None
        assert "memo-only" in found.note

    def test_unrecognised_ir_stays_unbound(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "bad-ir")
        _write_ir(exp, {"foo": 1})

        found = classify_legacy_workflow(exp)

        assert found.kind is None
        assert found.note is not None
        assert "not a recognised workflow IR" in found.note

    def test_handwritten_workflow_source_is_ignored(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "handwritten")
        reloaded = _stamp_workflow_source(exp, "train.py")

        found = classify_legacy_workflow(reloaded)

        assert found.kind is None

    def test_empty_experiment_stays_unbound(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "empty")

        found = classify_legacy_workflow(exp)

        assert found.kind is None
        assert found.note is None


class TestNeedsWorkflowKindMigration:
    def test_legacy_entrypoint_until_bound(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "entry")
        _set_metadata(exp, workflow_entrypoint=_ENTRYPOINT)

        assert needs_workflow_kind_migration(exp) is True

        exp.bind_workflow("code", entrypoint=_ENTRYPOINT)

        assert needs_workflow_kind_migration(exp) is False

    def test_handwritten_workflow_source_does_not_need_migration(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "handwritten")
        reloaded = _stamp_workflow_source(exp, "train.py")

        assert needs_workflow_kind_migration(reloaded) is False

    def test_plan_run_id_only_does_not_need_migration(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "plan")
        _set_metadata(exp, plan_run_id="p1")

        assert needs_workflow_kind_migration(exp) is False

    def test_brand_new_experiment_does_not_need_migration(self, tmp_path: Path) -> None:
        exp = _experiment(tmp_path, "fresh")

        assert needs_workflow_kind_migration(exp) is False
