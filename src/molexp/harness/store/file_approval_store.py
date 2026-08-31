"""File implementation of :class:`ApprovalStore`.

Persists ``request_id → {run_id, state, request, decision}`` as one JSON object
at ``path`` (typically ``run_dir/approvals.json``). Read-modify-write is
serialized with :func:`molexp.atomicio.file_lock` and written through
:class:`~molexp.workspace.FileStore.put`.

Replay law (the store's one non-obvious rule):

* **Grants replay.** A stored grant is durable consent — every later re-entry
  of the same request id passes on it without re-asking.
* **Rejections do not replay.** A rejection fails the *current* attempt and is
  kept as history, but a later :meth:`record_pending` for the same request id
  re-opens it as pending.
* A **granted** row is immutable to ``record_pending`` (never downgraded).
* ``record_decision`` on an unknown id raises :class:`ValueError`.
"""

from __future__ import annotations

import json
from pathlib import Path

from molexp.atomicio import file_lock
from molexp.harness.schemas import ApprovalDecision, ApprovalRequest
from molexp.workspace import FileStore

__all__ = ["FileApprovalStore"]

_Row = dict[str, object]


class FileApprovalStore:
    """JSON-file :class:`ApprovalStore` at ``path``."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._files = FileStore(root=self._path.parent)
        self._relpath = self._path.name
        self._lock_path = self._path.with_name(self._path.name + ".lock")

    def record_pending(self, run_id: str, request: ApprovalRequest) -> None:
        """Open (or re-open) *request* as pending.

        Idempotent on a pending row. A **granted** row is never downgraded.
        A **rejected** row is re-opened as pending.
        """
        with file_lock(self._lock_path):
            data = self._load()
            existing = data.get(request.id)
            if existing is not None and existing.get("state") == "granted":
                return
            data[request.id] = {
                "run_id": run_id,
                "state": "pending",
                "request": request.model_dump(mode="json"),
                "decision": None,
            }
            self._save(data)

    def record_decision(self, decision: ApprovalDecision) -> None:
        """Persist *decision* onto its pending request.

        Raises:
            ValueError: ``decision.request_id`` has no row in this store.
        """
        with file_lock(self._lock_path):
            data = self._load()
            existing = data.get(decision.request_id)
            if existing is None:
                raise ValueError(
                    f"approval decision for unknown request_id {decision.request_id!r} "
                    "— no pending request was ever recorded for it"
                )
            existing["state"] = "granted" if decision.granted else "rejected"
            existing["decision"] = decision.model_dump(mode="json")
            self._save(data)

    def granted_decision_for(self, request_id: str) -> ApprovalDecision | None:
        """Return the stored **grant** for *request_id*, or ``None``.

        Rejected and pending rows both return ``None`` — only a grant replays.
        """
        with file_lock(self._lock_path):
            row = self._load().get(request_id)
            if row is None or row.get("state") != "granted":
                return None
            raw = row.get("decision")
            if raw is None:
                raise ValueError(f"granted approval {request_id!r} has no stored decision")
            return ApprovalDecision.model_validate(raw)

    def pending(self, run_id: str) -> list[ApprovalRequest]:
        """Return every request of *run_id* still awaiting a decision."""
        with file_lock(self._lock_path):
            found: list[ApprovalRequest] = []
            for row in self._load().values():
                if row.get("run_id") == run_id and row.get("state") == "pending":
                    found.append(ApprovalRequest.model_validate(row["request"]))
            found.sort(key=lambda request: (request.created_at, request.id))
            return found

    def _load(self) -> dict[str, _Row]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"approvals file {self._path} is not a JSON object")
        out: dict[str, _Row] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValueError(f"malformed approval row {key!r} in {self._path}")
            out[key] = value
        return out

    def _save(self, data: dict[str, _Row]) -> None:
        self._files.put(self._relpath, data)
