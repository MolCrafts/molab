"""Disposable sharded JSON indexes for provenance-backed UI queries."""

from __future__ import annotations

from molexp._typing import JSONValue

from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .provenance import ProvenanceEvent, ProvenanceStore


class JsonIndexStore:
    """Derived one-file-per-entity/relation index with no shared append file."""

    def __init__(self, root: PathArg, *, fs: FileSystem | None = None) -> None:
        self.root = str(root)
        self.fs = fs or LocalFileSystem()

    @property
    def index_root(self) -> str:
        return self.fs.join(self.root, "index")

    def put_entity(self, entity_type: str, entity_id: str, record: dict[str, JSONValue]) -> None:
        path = self.fs.join(self.index_root, "entities", entity_type, f"{entity_id}.json")
        self.fs.mkdir(self.fs.dirname(path), parents=True, exist_ok=True)
        self.fs.atomic_write_json(
            path,
            {
                "schema_version": 2,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "record": record,
            },
        )

    def get_entity(self, entity_type: str, entity_id: str) -> dict[str, JSONValue] | None:
        path = self.fs.join(self.index_root, "entities", entity_type, f"{entity_id}.json")
        if not self.fs.exists(path):
            return None
        import json

        raw = json.loads(self.fs.read_text(path))
        record = raw.get("record")
        return record if isinstance(record, dict) else None

    def list_entities(self, entity_type: str) -> list[dict[str, JSONValue]]:
        base = self.fs.join(self.index_root, "entities", entity_type)
        if not self.fs.exists(base):
            return []
        import json

        records: list[dict[str, JSONValue]] = []
        for path in sorted(self.fs.glob(base, "*.json")):
            raw = json.loads(self.fs.read_text(path))
            record = raw.get("record")
            if isinstance(record, dict):
                records.append(record)
        return records

    def index_event(self, event: ProvenanceEvent) -> None:
        payload = event.model_dump(mode="json")
        self.put_entity("event", event.event_id, payload)
        record = event.attributes.get("record")
        if isinstance(record, dict):
            self.put_entity(event.subject.type, event.subject.id, record)
        refs = {event.subject.id, *(relation.object.id for relation in event.relations)}
        for entity_id in refs:
            path = self.fs.join(
                self.index_root,
                "relations",
                entity_id,
                f"{event.event_id}.json",
            )
            self.fs.mkdir(self.fs.dirname(path), parents=True, exist_ok=True)
            self.fs.atomic_write_json(path, {"schema_version": 2, "event": payload})

    def clear(self) -> None:
        if self.fs.exists(self.index_root):
            self.fs.remove(self.index_root, recursive=True)

    def rebuild(self, provenance: ProvenanceStore) -> int:
        self.clear()
        events = provenance.iter_events()
        for event in events:
            self.index_event(event)
        return len(events)


__all__ = ["JsonIndexStore"]
