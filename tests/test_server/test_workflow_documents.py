"""Unit tests for server workflow-document compile and binding migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.server.exceptions import ConflictError
from molab.server.workflow_documents import (
    compile_workflow_document,
    require_migrated_workflow_binding,
)
from molab.workspace import Workspace

DOC_A = {
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

BAD_DOC = {
    **DOC_A,
    "links": [
        *DOC_A["links"],
        {"source": "ghost", "target": "c", "mapping": {}, "status": "pending"},
    ],
}


def _experiment(tmp_path: Path):
    return Workspace(tmp_path / "lab", name="lab").add_project("p").add_experiment("e")


class TestCompileWorkflowDocument:
    def test_doc_a_returns_registration_spec(self) -> None:
        compiled = compile_workflow_document(DOC_A)

        assert isinstance(compiled, tuple)
        spec = compiled[0]
        assert sorted(spec.registration_by_name) == ["a", "b", "c"]

    def test_doc_a_second_item_is_dict(self) -> None:
        compiled = compile_workflow_document(DOC_A)

        assert isinstance(compiled[1], dict)

    def test_normalized_dict_recompiles_to_itself(self) -> None:
        normalized = compile_workflow_document(DOC_A)[1]

        again = compile_workflow_document(normalized)[1]

        assert again == normalized

    def test_unknown_link_source_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            compile_workflow_document(BAD_DOC)


class TestRequireMigratedWorkflowBinding:
    def test_legacy_entrypoint_raises_conflict(self, tmp_path: Path) -> None:
        experiment = _experiment(tmp_path)
        experiment.metadata = experiment.metadata.model_copy(
            update={"workflow_entrypoint": "wf.py:build"}
        )
        experiment.save()

        with pytest.raises(ConflictError) as exc_info:
            require_migrated_workflow_binding(experiment)

        assert exc_info.value.status_code == 409
        assert "molab migrate workflow-kind" in str(exc_info.value)

    def test_unbound_experiment_returns_none(self, tmp_path: Path) -> None:
        experiment = _experiment(tmp_path)

        assert require_migrated_workflow_binding(experiment) is None

    def test_code_binding_returns_none(self, tmp_path: Path) -> None:
        experiment = _experiment(tmp_path)
        experiment.bind_workflow("code", entrypoint="wf.py:build")

        assert require_migrated_workflow_binding(experiment) is None
