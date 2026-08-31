"""JSONL implementation of :class:`EventLog`.

One :class:`~molexp.harness.schemas.HarnessEvent` per line at ``path``
(typically ``run_dir/events.jsonl``). ``append`` assigns a 1-based per-``run_id``
``seq`` under :func:`molexp.atomicio.file_lock`; a missing file reads as ``[]``.
A bad JSON line makes :meth:`list_events` raise :class:`ValueError`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from molexp.atomicio import file_lock
from molexp.harness.schemas import EventType, HarnessEvent
from molexp.workspace import FileStore

__all__ = ["JsonlEventLog"]


class JsonlEventLog:
    """JSONL-backed append-only event log."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._files = FileStore(root=self._path.parent)
        self._relpath = self._path.name
        self._lock_path = self._path.with_name(self._path.name + ".lock")

    def append(
        self,
        run_id: str,
        type: EventType,
        actor: str,
        payload: dict[str, Any] | None = None,
        artifact_ids: list[str] | None = None,
    ) -> HarnessEvent:
        payload_obj = payload or {}
        ids = list(artifact_ids or [])
        with file_lock(self._lock_path):
            existing_seq = [event.seq for event in self._read_all() if event.run_id == run_id]
            seq = max(existing_seq, default=0) + 1
            event = HarnessEvent(
                id=uuid.uuid4().hex,
                run_id=run_id,
                seq=seq,
                type=type,
                actor=actor,
                created_at=datetime.now(tz=UTC),
                payload=payload_obj,
                artifact_ids=ids,
            )
            line = json.dumps(
                event.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False
            )
            self._files.append(self._relpath, line)
            return event

    def list_events(self, run_id: str) -> list[HarnessEvent]:
        with file_lock(self._lock_path):
            return [event for event in self._read_all() if event.run_id == run_id]

    def get_timeline(self, run_id: str) -> list[HarnessEvent]:
        return self.list_events(run_id)

    def _read_all(self) -> list[HarnessEvent]:
        if not self._path.exists():
            return []
        events: list[HarnessEvent] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in event log {self._path}: {exc}") from exc
            events.append(HarnessEvent.model_validate(data))
        return events
