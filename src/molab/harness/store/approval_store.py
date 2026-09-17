"""``ApprovalStore`` Protocol — persisted approval decisions.

The store is what turns approval from a per-process callback into a durable
resource: a gate consults it **before** asking anyone (store-first), a suspended
pipeline records its pending requests here so the server inbox can list them,
and a decision written here lets a ledger-resumed re-entry pass the gate.

Replay law (the store's one non-obvious rule):

* **Grants replay.** A stored grant is durable consent — every later re-entry
  of the same request id passes on it without re-asking.
* **Rejections do not replay.** A rejection fails the *current* attempt and is
  kept as history, but a later :meth:`ApprovalStore.record_pending` for the
  same request id re-opens it as pending — "not now" must never deadlock
  re-entry forever.
* A **granted** row is immutable to ``record_pending`` (never downgraded), so
  a decision racing a re-entry cannot be erased.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from molab.harness.schemas import ApprovalDecision, ApprovalRequest

__all__ = ["ApprovalStore"]


@runtime_checkable
class ApprovalStore(Protocol):
    """Structural type for any persisted-approval backend."""

    def record_pending(self, run_id: str, request: ApprovalRequest) -> None: ...

    def record_decision(self, decision: ApprovalDecision) -> None: ...

    def granted_decision_for(self, request_id: str) -> ApprovalDecision | None: ...

    def pending(self, run_id: str) -> list[ApprovalRequest]: ...
