"""Unit tests for experiment and workflow-document request models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from molab.server.schemas.requests import (
    ExperimentCreateRequest,
    WorkflowDocumentRequest,
)


class TestExperimentCreateRequest:
    def test_string_workflow_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentCreateRequest(name="e", workflow_source="x.py")

    def test_document_dict_is_kept(self) -> None:
        document = {"task_configs": [], "links": []}

        request = ExperimentCreateRequest(name="e", workflow_source=document)

        assert request.workflow_source == document

    def test_workflow_source_defaults_to_none(self) -> None:
        assert ExperimentCreateRequest(name="e").workflow_source is None


class TestWorkflowDocumentRequest:
    def test_convert_to_document_defaults_false(self) -> None:
        assert WorkflowDocumentRequest(document={}).convert_to_document is False

    def test_convert_to_document_camel_case_alias(self) -> None:
        request = WorkflowDocumentRequest.model_validate(
            {"document": {}, "convertToDocument": True}
        )

        assert request.convert_to_document is True
