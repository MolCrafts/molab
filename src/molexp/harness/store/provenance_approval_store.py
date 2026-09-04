"""ApprovalStore backed by append-only MolExp provenance events."""

from __future__ import annotations

from molexp.harness.schemas import ApprovalDecision, ApprovalRequest, ReviewDecision
from molexp.ids import generate_uuid7
from molexp.workspace.fs import FileSystem, PathArg
from molexp.workspace.provenance import (
    AgentRef,
    EntityRef,
    ProvenanceEvent,
    ProvenanceRelation,
    ProvenanceStore,
    create_event,
)

__all__ = ["ProvenanceApprovalStore"]


class ProvenanceApprovalStore:
    """Persist requests and decisions without editing an Execution record.

    Requests are related to the Execution that reached the gate. A later
    decision is a new fact related to that same Execution and logical Run.
    Retry Executions replay a grant by querying the graph.
    """

    def __init__(
        self,
        root: PathArg,
        *,
        run_id: str,
        execution_id: str,
        fs: FileSystem | None = None,
    ) -> None:
        self.run_id = run_id
        self.execution_id = execution_id
        self.provenance = ProvenanceStore(root, fs=fs)

    def record_pending(self, run_id: str, request: ApprovalRequest) -> None:
        if run_id != self.run_id:
            raise ValueError(f"approval belongs to Run {self.run_id!r}, not {run_id!r}")
        latest = self._latest(request.id)
        if latest is not None and latest.event_type == "ApprovalDecided":
            raw = latest.attributes.get("approval")
            if isinstance(raw, dict) and raw.get("granted") is True:
                return
        if (
            latest is not None
            and latest.event_type == "ApprovalRequested"
            and latest.attributes.get("execution_id") == self.execution_id
        ):
            return
        self.provenance.append(
            create_event(
                "ApprovalRequested",
                subject=EntityRef(id=request.id, type="approval-request"),
                agent=AgentRef(id="molexp", type="system", name="MolExp"),
                relations=self._relations(),
                attributes={
                    "run_id": self.run_id,
                    "execution_id": self.execution_id,
                    "request": request.model_dump(mode="json"),
                },
                occurred_at=request.created_at,
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

    def granted_decision_for(self, request_id: str) -> ApprovalDecision | None:
        latest = self._latest(request_id)
        if latest is None or latest.event_type != "ApprovalDecided":
            return None
        raw = latest.attributes.get("approval")
        if not isinstance(raw, dict) or raw.get("granted") is not True:
            return None
        return ApprovalDecision.model_validate(raw)

    def pending(self, run_id: str) -> list[ApprovalRequest]:
        if run_id != self.run_id:
            return []
        latest_by_request: dict[str, ProvenanceEvent] = {}
        for event in self._events():
            latest_by_request[event.subject.id] = event
        requests: list[ApprovalRequest] = []
        for event in latest_by_request.values():
            if event.event_type != "ApprovalRequested":
                continue
            raw = event.attributes.get("request")
            if isinstance(raw, dict):
                requests.append(ApprovalRequest.model_validate(raw))
        return sorted(requests, key=lambda item: (item.created_at, item.id))

    def latest_review_decision(self) -> ReviewDecision | None:
        """Return the most recent structured review affecting this Run."""
        decided = [event for event in self._events() if event.event_type == "ApprovalDecided"]
        for event in reversed(decided):
            raw = event.attributes.get("review")
            if isinstance(raw, dict):
                return ReviewDecision.model_validate(raw)
        return None

    def _record_decision(
        self,
        decision: ApprovalDecision,
        *,
        review: ReviewDecision | None,
    ) -> None:
        if not any(
            event.event_type == "ApprovalRequested"
            for event in self._request_events(decision.request_id)
        ):
            raise ValueError(f"approval decision for unknown request_id {decision.request_id!r}")
        attributes = {
            "run_id": self.run_id,
            "execution_id": self.execution_id,
            "approval": decision.model_dump(mode="json"),
        }
        if review is not None:
            attributes["review"] = review.model_dump(mode="json")
        self.provenance.append(
            create_event(
                "ApprovalDecided",
                subject=EntityRef(id=decision.request_id, type="approval-request"),
                agent=AgentRef(
                    id=decision.decided_by,
                    type="person",
                    name=decision.decided_by,
                ),
                relations=self._relations(),
                attributes=attributes,
                occurred_at=decision.decided_at,
                event_id=generate_uuid7(),
            )
        )

    def _relations(self) -> tuple[ProvenanceRelation, ...]:
        return (
            ProvenanceRelation(
                predicate="wasAssociatedWith",
                object=EntityRef(id=self.execution_id, type="execution"),
            ),
            ProvenanceRelation(
                predicate="pertainsTo",
                object=EntityRef(id=self.run_id, type="run"),
            ),
        )

    def _events(self) -> list[ProvenanceEvent]:
        return sorted(
            (
                event
                for event in self.provenance.events_for(self.run_id)
                if event.event_type in {"ApprovalRequested", "ApprovalDecided"}
                and event.attributes.get("run_id") == self.run_id
            ),
            key=lambda event: (event.occurred_at, event.event_id),
        )

    def _request_events(self, request_id: str) -> list[ProvenanceEvent]:
        return [event for event in self._events() if event.subject.id == request_id]

    def _latest(self, request_id: str) -> ProvenanceEvent | None:
        events = self._request_events(request_id)
        return events[-1] if events else None
