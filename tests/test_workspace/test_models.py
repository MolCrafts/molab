"""Unit tests for ``molab.workspace.models`` (``ExperimentMetadata``).

arch-own-04a ac-001: ``workflow_kind`` is optional and closed over
``"code"`` / ``"document"``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from molab.workspace.models import ExperimentMetadata

_REQUIRED = {
    "id": "exp-1",
    "name": "demo",
    "revision_id": "rev-1",
    "definition_hash": "sha256:abc",
}


class TestExperimentMetadata:
    def test_workflow_kind_defaults_to_none(self) -> None:
        meta = ExperimentMetadata(**_REQUIRED)

        assert meta.workflow_kind is None

    def test_code_kind_constructs(self) -> None:
        meta = ExperimentMetadata(**_REQUIRED, workflow_kind="code")

        assert meta.workflow_kind == "code"

    def test_document_kind_constructs(self) -> None:
        meta = ExperimentMetadata(**_REQUIRED, workflow_kind="document")

        assert meta.workflow_kind == "document"

    def test_script_kind_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentMetadata(**_REQUIRED, workflow_kind="script")  # type: ignore[arg-type]

    def test_model_validate_without_workflow_kind_is_none(self) -> None:
        meta = ExperimentMetadata.model_validate(dict(_REQUIRED))

        assert meta.workflow_kind is None

    def test_workflow_kind_is_exported_from_workspace(self) -> None:
        import molab.workspace as workspace
        from molab.workspace import WorkflowKind

        assert "WorkflowKind" in workspace.__all__
        assert workspace.WorkflowKind is WorkflowKind

    def test_legacy_fields_are_not_on_the_model(self) -> None:
        assert {"workflow_source", "workflow_type", "git_commit"}.isdisjoint(
            ExperimentMetadata.model_fields
        )

    def test_legacy_payload_drops_removed_keys(self) -> None:
        meta = ExperimentMetadata.model_validate(
            {
                **_REQUIRED,
                "workflow_source": "train.py",
                "workflow_type": "yaml",
                "git_commit": "abc123",
            }
        )
        dumped = meta.model_dump()
        assert "workflow_source" not in dumped
        assert "workflow_type" not in dumped
        assert "git_commit" not in dumped
