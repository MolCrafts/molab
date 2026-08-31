"""Public-API regression for persist-one-03-harness-files.

Hard-coded golden: ``JsonlEventLog`` seq ``[1, 2]``; ``FileLineageStore``
A→B→C ``trace_backward(C)`` ids ``[B, A]``; ``FileApprovalStore`` grant
replays; ``(run_dir / "harness.sqlite").exists()`` is False; events land at
``run_dir/events.jsonl``. Public ``molexp.harness`` API only. No third-party
runtime.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from molexp.harness import (
    FileApprovalStore,
    FileArtifactStore,
    FileLineageStore,
    JsonlEventLog,
)
from molexp.harness.schemas import ApprovalDecision, ApprovalRequest


def main() -> None:
    run_dir = Path(tempfile.mkdtemp(prefix="persist-one-03-harness-files-"))

    events = JsonlEventLog(path=run_dir / "events.jsonl")
    first = events.append(run_id="run-1", type="run_created", actor="harness")
    second = events.append(run_id="run-1", type="stage_started", actor="harness")
    assert [first.seq, second.seq] == [1, 2]
    assert [e.seq for e in events.list_events("run-1")] == [1, 2]
    assert (run_dir / "events.jsonl").is_file()

    artifacts = FileArtifactStore(root=run_dir / "artifacts")
    lineage = FileLineageStore(artifact_store=artifacts)
    artifact_a = artifacts.put_json(
        kind="user_plan", obj={"a": 1}, created_by="user", parent_ids=[]
    )
    artifact_b = artifacts.put_json(
        kind="experiment_report",
        obj={"b": 1},
        created_by="harness",
        parent_ids=[artifact_a.id],
    )
    artifact_c = artifacts.put_json(
        kind="workflow_ir",
        obj={"c": 1},
        created_by="harness",
        parent_ids=[artifact_b.id],
    )
    lineage.add_edge(artifact_a.id, artifact_b.id)
    lineage.add_edge(artifact_b.id, artifact_c.id)
    assert [ref.id for ref in lineage.trace_backward(artifact_c.id)] == [
        artifact_b.id,
        artifact_a.id,
    ]

    approvals = FileApprovalStore(path=run_dir / "approvals.json")
    request = ApprovalRequest(
        id="req-1",
        intent="experiment_spec",
        reason="approve",
        triggered_by_policy="regression",
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
    )
    approvals.record_pending("run-1", request)
    approvals.record_decision(
        ApprovalDecision(
            request_id="req-1",
            granted=True,
            decided_by="tester",
            decided_at=datetime(2026, 8, 31, 12, tzinfo=UTC),
        )
    )
    grant = approvals.granted_decision_for("req-1")
    assert grant is not None
    assert grant.granted is True
    approvals.record_pending("run-1", request)
    assert approvals.granted_decision_for("req-1") is not None
    assert approvals.pending("run-1") == []

    assert (run_dir / "harness.sqlite").exists() is False
    print("persist-one-03-harness-files: ok")


if __name__ == "__main__":
    main()
