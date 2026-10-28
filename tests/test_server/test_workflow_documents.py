"""Unit tests for server workflow-document compile."""

from __future__ import annotations

import pytest

from molab.server.workflow_documents import compile_workflow_document

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
