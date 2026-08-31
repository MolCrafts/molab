"""``FileApprovalStore`` grant-replay laws against ``approvals.json``.

Port of the vision-loop-01 store laws onto the file backend
(persist-one-03-harness-files):

* **Grants replay** — a stored grant is durable consent; ``granted_decision_for``
  returns it on every later re-entry.
* **Rejections never replay** — recorded as history, but ``granted_decision_for``
  returns ``None`` and a later ``record_pending`` re-opens the request pending.
* ``record_pending`` never downgrades a *granted* row back to pending.
* ``record_decision`` on an unknown ``request_id`` fails loud — no fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from molexp.harness.schemas import ApprovalDecision, ApprovalRequest

if TYPE_CHECKING:
    from molexp.harness.store.file_approval_store import FileApprovalStore

_RUN_ID = "run-approvals"


def _request(request_id: str = "req-1") -> ApprovalRequest:
    return ApprovalRequest(
        id=request_id,
        intent="experiment_spec",
        reason="approve the concrete experiment spec",
        triggered_by_policy="PlanMode",
        metadata={"execution_backend": "local"},
        created_at=datetime(2026, 7, 3, tzinfo=UTC),
    )


def _decision(
    request_id: str = "req-1",
    *,
    granted: bool,
    decided_by: str = "tester",
    reason: str | None = None,
) -> ApprovalDecision:
    return ApprovalDecision(
        request_id=request_id,
        granted=granted,
        decided_by=decided_by,
        decided_at=datetime(2026, 7, 3, 12, 0, tzinfo=UTC),
        reason=reason,
    )


@pytest.fixture()
def store(tmp_path: Path) -> FileApprovalStore:
    from molexp.harness.store.file_approval_store import FileApprovalStore

    return FileApprovalStore(path=tmp_path / "approvals.json")


class TestFileApprovalStore:
    def test_grant_replays_and_clears_pending(self, store: FileApprovalStore) -> None:
        request = _request()
        store.record_pending(_RUN_ID, request)
        store.record_decision(_decision(granted=True, decided_by="ui-operator", reason="ok"))

        stored = store.granted_decision_for(request.id)
        assert stored is not None
        assert stored.request_id == request.id
        assert stored.granted is True
        assert stored.decided_by == "ui-operator"
        assert stored.reason == "ok"
        assert store.pending(_RUN_ID) == []

    def test_rejection_is_recorded_but_never_replays(self, store: FileApprovalStore) -> None:
        request = _request()
        store.record_pending(_RUN_ID, request)
        store.record_decision(_decision(granted=False, reason="not now"))

        assert store.granted_decision_for(request.id) is None
        assert store.pending(_RUN_ID) == []

    def test_record_pending_after_rejection_reopens_pending(self, store: FileApprovalStore) -> None:
        request = _request()
        store.record_pending(_RUN_ID, request)
        store.record_decision(_decision(granted=False, reason="not now"))

        store.record_pending(_RUN_ID, request)
        [reopened] = store.pending(_RUN_ID)
        assert reopened.id == request.id
        assert store.granted_decision_for(request.id) is None

    def test_record_pending_never_downgrades_a_granted_row(self, store: FileApprovalStore) -> None:
        request = _request()
        store.record_pending(_RUN_ID, request)
        store.record_decision(_decision(granted=True, decided_by="ui-operator"))

        store.record_pending(_RUN_ID, request)

        stored = store.granted_decision_for(request.id)
        assert stored is not None
        assert stored.decided_by == "ui-operator"
        assert store.pending(_RUN_ID) == []

    def test_record_decision_on_unknown_request_id_raises(self, store: FileApprovalStore) -> None:
        with pytest.raises(ValueError, match="request_id"):
            store.record_decision(_decision("req-never-recorded", granted=True))

    def test_persists_to_approvals_json_not_sqlite(
        self, store: FileApprovalStore, tmp_path: Path
    ) -> None:
        store.record_pending(_RUN_ID, _request())
        assert (tmp_path / "approvals.json").is_file()
        assert not (tmp_path / "harness.sqlite").exists()
