"""Tests for ``PlanArtifactRef`` (``molexp.harness.schemas.artifact``).

Locks the two non-obvious wire contracts: ``kind`` is an open ``str`` (agent
layers register their own kinds without touching the schema module), and
``sha256`` is bare hex (callers must strip the workspace ``sha256:`` prefix).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from molexp.harness.schemas.artifact import PlanArtifactRef


class TestPlanArtifactRef:
    def test_sha256_rejects_prefixed_form(self) -> None:
        """The ``sha256:`` prefix must be stripped by FileArtifactStore first."""
        with pytest.raises(ValidationError):
            PlanArtifactRef(
                id="a1b2c3d4",
                kind="log",
                uri="file:///x",
                sha256="sha256:" + "a" * 64,
                created_at=datetime(2026, 5, 26, tzinfo=UTC),
                created_by="harness",
            )
