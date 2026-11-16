"""Unit tests for experiment and workflow-document request models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from molab.server.schemas.requests import (
    ExecutionAttemptCreateRequest,
    ExecutionCreateRequest,
    ExperimentCreateRequest,
    RunCreateRequest,
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


class TestRunParamRequests:
    def test_params_is_accepted(self) -> None:
        request = RunCreateRequest.model_validate({"params": {"seed": 1}})

        assert request.params == {"seed": 1}

    def test_parameters_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="parameters"):
            RunCreateRequest.model_validate({"parameters": {"seed": 1}})

    def test_parameters_beside_params_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="parameters"):
            RunCreateRequest.model_validate({"params": {"seed": 1}, "parameters": {"seed": 2}})

    def test_execution_create_rejects_parameters(self) -> None:
        with pytest.raises(ValidationError, match="parameters"):
            ExecutionCreateRequest.model_validate(
                {"projectId": "p", "experimentId": "e", "parameters": {"seed": 1}}
            )

        request = ExecutionCreateRequest.model_validate(
            {"projectId": "p", "experimentId": "e", "params": {"seed": 1}}
        )
        assert request.params == {"seed": 1}


class TestExecutionAttemptCreateRequest:
    def test_retry_mode_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionAttemptCreateRequest.model_validate({"mode": "retry"})

    def test_rerun_mode_is_accepted(self) -> None:
        request = ExecutionAttemptCreateRequest.model_validate({"mode": "rerun"})

        assert request.mode == "rerun"
