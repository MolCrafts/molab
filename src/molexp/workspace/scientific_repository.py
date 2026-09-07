"""Record scientific intent — Project, Experiment revision, Run — in history.

The entity JSON files are the declarations; this class only commits them so
the workspace's git log reads as a scientific narrative rather than a series
of anonymous file changes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from molexp._typing import JSONValue

from .fs import FileSystem, PathArg
from .fs_local import LocalFileSystem
from .history import SYSTEM_AGENT, EntityRef, GitHistory, Relation

__all__ = ["SYSTEM_AGENT", "ScientificRepository"]


def _when(record: dict[str, JSONValue], key: str) -> datetime:
    raw = record.get(key)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(UTC)


class ScientificRepository:
    """Commit each declaration with a typed fact in the message trailers."""

    def __init__(
        self,
        workspace_root: PathArg,
        *,
        fs: FileSystem | None = None,
        history: GitHistory | None = None,
    ) -> None:
        self.root = str(workspace_root)
        self.fs = fs or LocalFileSystem()
        self.history = history or GitHistory(self.root)

    def record_project(
        self,
        record: dict[str, JSONValue],
        *,
        workspace_id: str,
        path: PathArg | None = None,
    ) -> None:
        self.history.record(
            "ProjectCreated",
            subject=EntityRef(id=str(record["id"]), type="project"),
            agent=SYSTEM_AGENT,
            relations=(
                Relation(
                    predicate="wasAttributedTo",
                    object=EntityRef(id=workspace_id, type="workspace"),
                ),
            ),
            summary=str(record.get("name") or record["id"]),
            paths=(path,) if path else (),
            occurred_at=_when(record, "created_at"),
        )

    def record_experiment(
        self,
        record: dict[str, JSONValue],
        *,
        project_id: str,
        path: PathArg | None = None,
    ) -> None:
        self.history.record(
            "ExperimentCreated",
            subject=EntityRef(id=str(record["id"]), type="experiment"),
            agent=SYSTEM_AGENT,
            relations=(
                Relation(predicate="partOf", object=EntityRef(id=project_id, type="project")),
                Relation(
                    predicate="hasRevision",
                    object=EntityRef(id=str(record["revision_id"]), type="experiment-revision"),
                ),
            ),
            summary=str(record.get("name") or record["id"]),
            paths=(path,) if path else (),
            occurred_at=_when(record, "created_at"),
        )

    def record_experiment_revision(
        self,
        record: dict[str, JSONValue],
        *,
        project_id: str,
        path: PathArg | None = None,
    ) -> None:
        self.history.record(
            "ExperimentRevised",
            subject=EntityRef(id=str(record["revision_id"]), type="experiment-revision"),
            agent=SYSTEM_AGENT,
            relations=(
                Relation(
                    predicate="revisionOf",
                    object=EntityRef(id=str(record["id"]), type="experiment"),
                ),
                Relation(predicate="partOf", object=EntityRef(id=project_id, type="project")),
            ),
            summary=f"{record.get('name') or record['id']} rev {record.get('revision', '?')}",
            paths=(path,) if path else (),
            occurred_at=_when(record, "revision_created_at"),
        )

    def record_run(
        self,
        record: dict[str, JSONValue],
        *,
        experiment_id: str,
        path: PathArg | None = None,
    ) -> None:
        relations = [
            Relation(
                predicate="instanceOf",
                object=EntityRef(
                    id=str(record["experiment_revision_id"]), type="experiment-revision"
                ),
            ),
            Relation(predicate="partOf", object=EntityRef(id=experiment_id, type="experiment")),
        ]
        raw_ids = record.get("input_asset_ids", [])
        if isinstance(raw_ids, list):
            relations.extend(
                Relation(predicate="uses", object=EntityRef(id=str(value), type="asset"))
                for value in raw_ids
            )
        name = self.fs.basename(str(path)) if path else str(record["id"])
        self.history.record(
            "RunDefined",
            subject=EntityRef(id=str(record["id"]), type="run"),
            agent=SYSTEM_AGENT,
            relations=tuple(relations),
            summary=name,
            paths=(path,) if path else (),
            occurred_at=_when(record, "created_at"),
        )
