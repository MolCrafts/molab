"""RED tests for the plan-emergent-06 intervention data contract.

Pins the blocked-task error the realization phase raises when a task cannot be
self-repaired to green: ``TaskRealizationBlockedError`` subclasses
``StageExecutionError`` (so existing ``except StageExecutionError`` sites still
stop the pipeline) and carries ``request_ref`` + ``blocked_task_ids``.

The production modules do not exist yet: an ``ImportError`` at collection time
is the valid RED signal.
"""

from __future__ import annotations

from datetime import UTC, datetime

from molexp.harness.errors import StageExecutionError, TaskRealizationBlockedError
from molexp.harness.schemas import PlanArtifactRef


def _ref(kind: str = "intervention_request") -> PlanArtifactRef:
    """A structurally valid ``PlanArtifactRef`` (bare-hex sha256)."""
    return PlanArtifactRef(
        id="art-intervention-1",
        kind=kind,
        uri="mem://art-intervention-1",
        sha256="a" * 64,
        created_at=datetime(2026, 7, 22, tzinfo=UTC),
        created_by="test",
    )


class TestTaskRealizationBlockedError:
    def test_carries_request_ref_and_blocked_task_ids(self) -> None:
        ref = _ref()
        err = TaskRealizationBlockedError(ref, ["b-beta"])
        assert isinstance(err, StageExecutionError)
        assert err.request_ref is ref
        assert err.blocked_task_ids == ["b-beta"]
