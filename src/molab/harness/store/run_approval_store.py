"""ApprovalStore backed by one append-only JSONL file per Run.

Approvals are facts about a Run that outlive any single attempt: a grant
recorded during ``e01`` must still be visible to the retry in ``e02``. So the
log sits at the run root — ``<run_dir>/approvals.jsonl`` — one line per fact,
never rewritten. A retry replays a grant by reading the same file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from molab.atomicio import file_lock
from molab.harness.schemas import ApprovalDecision, ApprovalRequest, ReviewDecision

__all__ = ["RunApprovalStore"]

APPROVALS_FILENAME = "approvals.jsonl"


class ApprovalFact(BaseModel):
    """One immutable line of the approval log."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["requested", "decided"]
    request_id: str
    run_id: str
    execution_id: str
    at: datetime
    request: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    review: dict[str, Any] | None = None


class RunApprovalStore:
    """Persist requests and decisions beside the Run they gate."""

    def __init__(
        self,
        run_dir: Path | str,
        *,
        run_id: str,
        execution_id: str,
    ) -> None:
        self.run_dir = Path(str(run_dir))
        self.run_id = run_id
        self.execution_id = execution_id

    @property
    def path(self) -> Path:
        return self.run_dir / APPROVALS_FILENAME

    # ── write ────────────────────────────────────────────────────────────

    def record_pending(self, run_id: str, request: ApprovalRequest) -> None:
        if run_id != self.run_id:
            raise ValueError(f"approval belongs to Run {self.run_id!r}, not {run_id!r}")
        latest = self._latest(request.id)
        if latest is not None and latest.kind == "decided":
            approval = latest.approval or {}
            if approval.get("granted") is True:
                return
        if (
            latest is not None
            and latest.kind == "requested"
            and latest.execution_id == self.execution_id
        ):
            return
        self._append(
            ApprovalFact(
                kind="requested",
                request_id=request.id,
                run_id=self.run_id,
                execution_id=self.execution_id,
                at=request.created_at,
                request=request.model_dump(mode="json"),
            )
        )

    def record_decision(self, decision: ApprovalDecision) -> None:
        self._record_decision(decision, review=None)

    def record_review_decision(
        self,
        decision: ApprovalDecision,
        review: ReviewDecision,
    ) -> None:
        """Append the richer UI/CLI review and its binary gate projection."""
        self._record_decision(decision, review=review)

    # ── read ─────────────────────────────────────────────────────────────

    def granted_decision_for(self, request_id: str) -> ApprovalDecision | None:
        latest = self._latest(request_id)
        if latest is None or latest.kind != "decided":
            return None
        approval = latest.approval or {}
        if approval.get("granted") is not True:
            return None
        return ApprovalDecision.model_validate(approval)

    def pending(self, run_id: str) -> list[ApprovalRequest]:
        if run_id != self.run_id:
            return []
        latest_by_request: dict[str, ApprovalFact] = {}
        for fact in self._facts():
            latest_by_request[fact.request_id] = fact
        requests = [
            ApprovalRequest.model_validate(fact.request)
            for fact in latest_by_request.values()
            if fact.kind == "requested" and fact.request is not None
        ]
        return sorted(requests, key=lambda item: (item.created_at, item.id))

    def latest_review_decision(self) -> ReviewDecision | None:
        """Return the most recent structured review affecting this Run."""
        for fact in reversed(self._facts()):
            if fact.kind == "decided" and fact.review is not None:
                return ReviewDecision.model_validate(fact.review)
        return None

    # ── internals ────────────────────────────────────────────────────────

    def _record_decision(
        self,
        decision: ApprovalDecision,
        *,
        review: ReviewDecision | None,
    ) -> None:
        if not any(
            fact.kind == "requested" and fact.request_id == decision.request_id
            for fact in self._facts()
        ):
            raise ValueError(f"approval decision for unknown request_id {decision.request_id!r}")
        self._append(
            ApprovalFact(
                kind="decided",
                request_id=decision.request_id,
                run_id=self.run_id,
                execution_id=self.execution_id,
                at=decision.decided_at,
                approval=decision.model_dump(mode="json"),
                review=review.model_dump(mode="json") if review is not None else None,
            )
        )

    def _facts(self) -> list[ApprovalFact]:
        if not self.path.exists():
            return []
        facts: list[ApprovalFact] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            facts.append(ApprovalFact.model_validate(json.loads(line)))
        return sorted(facts, key=lambda item: (item.at, item.kind))

    def _latest(self, request_id: str) -> ApprovalFact | None:
        matching = [fact for fact in self._facts() if fact.request_id == request_id]
        return matching[-1] if matching else None

    def _append(self, fact: ApprovalFact) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".jsonl.lock")
        with file_lock(lock), self.path.open("a", encoding="utf-8") as handle:
            handle.write(fact.model_dump_json() + "\n")
