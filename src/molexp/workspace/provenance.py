"""Portable append-only provenance facts for MolExp v2.

The event files in ``provenance/events`` are canonical scientific history.
Workspace folders and JSON indexes are materialized views and may be rebuilt.
Each event is immutable, self-verifying, and uses stable entity identities;
paths may appear only as descriptive attributes, never as identity.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from molexp._typing import JSONValue
from molexp.ids import generate_uuid7

from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem

PROVENANCE_SCHEMA = "https://molexp.org/schemas/provenance-event/v2"


class EntityRef(BaseModel):
    """Stable reference to a provenance Entity or Activity."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str

    @property
    def urn(self) -> str:
        return f"urn:molexp:{self.type}:{self.id}"


class AgentRef(BaseModel):
    """Person, software, workflow, or executor responsible for a fact."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: Literal["person", "software", "workflow", "executor", "system"]
    name: str | None = None


class ProvenanceRelation(BaseModel):
    """One directed, W3C-PROV-compatible relationship."""

    model_config = ConfigDict(frozen=True)

    predicate: str
    object: EntityRef
    attributes: dict[str, JSONValue] = Field(default_factory=dict)


class ProvenanceEvent(BaseModel):
    """One immutable provenance fact stored as an independent JSON object."""

    model_config = ConfigDict(frozen=True)

    schema_uri: str = PROVENANCE_SCHEMA
    schema_version: Literal[2] = 2
    event_id: str
    event_type: str
    occurred_at: datetime
    subject: EntityRef
    agent: AgentRef
    relations: tuple[ProvenanceRelation, ...] = ()
    attributes: dict[str, JSONValue] = Field(default_factory=dict)
    digest: str

    @model_validator(mode="after")
    def _digest_matches(self) -> ProvenanceEvent:
        expected = event_digest(self)
        if self.digest != expected:
            raise ValueError(
                f"provenance event {self.event_id!r} digest mismatch: "
                f"expected {expected}, got {self.digest}"
            )
        return self


def _digest_payload(event: ProvenanceEvent | dict[str, object]) -> dict[str, object]:
    if isinstance(event, ProvenanceEvent):
        return event.model_dump(mode="json", exclude={"digest"})
    return {key: value for key, value in event.items() if key != "digest"}


def event_digest(event: ProvenanceEvent | dict[str, object]) -> str:
    """Return the canonical SHA-256 digest of an event without its digest field."""
    encoded = json.dumps(
        _digest_payload(event),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def create_event(
    event_type: str,
    *,
    subject: EntityRef,
    agent: AgentRef,
    relations: tuple[ProvenanceRelation, ...] = (),
    attributes: dict[str, JSONValue] | None = None,
    occurred_at: datetime | None = None,
    event_id: str | None = None,
) -> ProvenanceEvent:
    """Construct a valid immutable event with a stable UUIDv7 identity."""
    draft = ProvenanceEvent.model_construct(
        schema_uri=PROVENANCE_SCHEMA,
        schema_version=2,
        event_id=event_id or generate_uuid7(),
        event_type=event_type,
        occurred_at=occurred_at or datetime.now(UTC),
        subject=subject,
        agent=agent,
        relations=relations,
        attributes=attributes or {},
        digest="",
    )
    return ProvenanceEvent.model_validate(
        draft.model_copy(update={"digest": event_digest(draft)}).model_dump(mode="json")
    )


class ProvenanceStore:
    """Filesystem/object-store-friendly append-only event repository."""

    def __init__(self, root: PathArg, *, fs: FileSystem | None = None) -> None:
        self.root = str(root)
        self.fs = fs or LocalFileSystem()

    def _event_path(self, event: ProvenanceEvent) -> str:
        occurred = event.occurred_at.astimezone(UTC)
        return self.fs.join(
            self.root,
            "provenance",
            "events",
            f"{occurred.year:04d}",
            f"{occurred.month:02d}",
            f"{event.event_id}.json",
        )

    def append(self, event: ProvenanceEvent) -> str:
        """Append *event* once; an existing different event is corruption."""
        path = self._event_path(event)
        if self.fs.exists(path):
            existing = ProvenanceEvent.model_validate_json(self.fs.read_text(path))
            if existing.digest != event.digest:
                raise FileExistsError(
                    f"event id collision: {event.event_id!r} already has another digest"
                )
            return path
        self.fs.mkdir(self.fs.dirname(path), parents=True, exist_ok=True)
        self.fs.atomic_write_json(path, event.model_dump(mode="json"))
        return path

    def iter_events(self) -> list[ProvenanceEvent]:
        base = self.fs.join(self.root, "provenance", "events")
        if not self.fs.exists(base):
            return []
        paths = sorted(self.fs.rglob(base, "*.json"))
        return [ProvenanceEvent.model_validate_json(self.fs.read_text(path)) for path in paths]

    def events_for(self, entity_id: str) -> list[ProvenanceEvent]:
        return [
            event
            for event in self.iter_events()
            if event.subject.id == entity_id
            or any(relation.object.id == entity_id for relation in event.relations)
        ]


__all__ = [
    "PROVENANCE_SCHEMA",
    "AgentRef",
    "EntityRef",
    "ProvenanceEvent",
    "ProvenanceRelation",
    "ProvenanceStore",
    "create_event",
    "event_digest",
]
