"""Append-only declarations for Project, Experiment revisions, and Runs."""

from __future__ import annotations

from datetime import UTC, datetime

from molexp._typing import JSONValue

from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .index_store import JsonIndexStore
from .provenance import (
    AgentRef,
    EntityRef,
    ProvenanceRelation,
    ProvenanceStore,
    create_event,
)

SYSTEM_AGENT = AgentRef(id="molexp", type="system", name="MolExp")


class ScientificRepository:
    """Persist scientific intent as provenance, separate from folder views."""

    def __init__(
        self,
        workspace_root: PathArg,
        *,
        fs: FileSystem | None = None,
        provenance: ProvenanceStore | None = None,
        index: JsonIndexStore | None = None,
    ) -> None:
        self.root = str(workspace_root)
        self.fs = fs or LocalFileSystem()
        self.provenance = provenance or ProvenanceStore(self.root, fs=self.fs)
        self.index = index or JsonIndexStore(self.root, fs=self.fs)

    def record_project(self, record: dict[str, JSONValue], *, workspace_id: str) -> None:
        self._append_once(
            "ProjectCreated",
            EntityRef(id=str(record["id"]), type="project"),
            relations=(
                ProvenanceRelation(
                    predicate="wasAttributedTo",
                    object=EntityRef(id=workspace_id, type="workspace"),
                ),
            ),
            record=record,
        )

    def record_experiment(
        self,
        record: dict[str, JSONValue],
        *,
        project_id: str,
    ) -> None:
        experiment_id = str(record["id"])
        self._append_once(
            "ExperimentCreated",
            EntityRef(id=experiment_id, type="experiment"),
            relations=(
                ProvenanceRelation(
                    predicate="partOf",
                    object=EntityRef(id=project_id, type="project"),
                ),
            ),
            record=record,
        )
        self.record_experiment_revision(record, project_id=project_id)

    def record_experiment_revision(
        self,
        record: dict[str, JSONValue],
        *,
        project_id: str,
    ) -> None:
        revision_id = str(record["revision_id"])
        self._append_once(
            "ExperimentRevisionCreated",
            EntityRef(id=revision_id, type="experiment-revision"),
            relations=(
                ProvenanceRelation(
                    predicate="revisionOf",
                    object=EntityRef(id=str(record["id"]), type="experiment"),
                ),
                ProvenanceRelation(
                    predicate="partOf",
                    object=EntityRef(id=project_id, type="project"),
                ),
            ),
            record=record,
        )

    def record_run(
        self,
        record: dict[str, JSONValue],
        *,
        experiment_id: str,
    ) -> None:
        relations = [
            ProvenanceRelation(
                predicate="instanceOf",
                object=EntityRef(
                    id=str(record["experiment_revision_id"]),
                    type="experiment-revision",
                ),
            ),
            ProvenanceRelation(
                predicate="partOf",
                object=EntityRef(id=experiment_id, type="experiment"),
            ),
        ]
        raw_ids = record.get("input_asset_ids", [])
        asset_ids = raw_ids if isinstance(raw_ids, list) else []
        for asset_id in asset_ids:
            relations.append(
                ProvenanceRelation(
                    predicate="uses",
                    object=EntityRef(id=str(asset_id), type="asset"),
                )
            )
        self._append_once(
            "RunDefined",
            EntityRef(id=str(record["id"]), type="run"),
            relations=tuple(relations),
            record=record,
        )

    def _append_once(
        self,
        event_type: str,
        subject: EntityRef,
        *,
        relations: tuple[ProvenanceRelation, ...],
        record: dict[str, JSONValue],
    ) -> None:
        if any(
            event.event_type == event_type and event.subject == subject
            for event in self.provenance.events_for(subject.id)
        ):
            return
        occurred_at_raw = record.get(
            "revision_created_at" if event_type == "ExperimentRevisionCreated" else "created_at"
        )
        occurred_at = (
            datetime.fromisoformat(occurred_at_raw)
            if isinstance(occurred_at_raw, str)
            else datetime.now(UTC)
        )
        event = create_event(
            event_type,
            subject=subject,
            agent=SYSTEM_AGENT,
            relations=relations,
            attributes={"record": record},
            occurred_at=occurred_at,
        )
        self.provenance.append(event)
        self.index.index_event(event)


__all__ = ["SYSTEM_AGENT", "ScientificRepository"]
