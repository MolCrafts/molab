"""Chronological research replay, projected from existing records and git facts.

This is a read-model, never another event store. Saved attempts fill gaps when
the best-effort history missed a commit; git keeps earlier document versions.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from difflib import unified_diff
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from molab._typing import JSONValue
from molab.knowledge.frontmatter import split_frontmatter
from molab.knowledge.naming import is_knowledge_file
from molab.workspace import Experiment, Project, Run, Workspace
from molab.workspace.domain import ExecutionOrigin
from molab.workspace.fs_local import LocalFS
from molab.workspace.history import AgentRef, FileRevision, GitHistory
from molab.workspace.refs import MolabRef, ref_of
from molab.workspace.scope import as_folder, descendants, resolve_in_scope


class ReplayEvent(BaseModel):
    """One dated, evidence-backed step; details are recorded facts, not inferred intent."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    at: datetime
    kind: Literal["experiment", "run", "execution", "knowledge", "asset", "history"]
    action: str
    title: str
    ref: str | None = None
    actor: AgentRef | None = None
    commit: str | None = None
    document: str | None = None
    details: dict[str, JSONValue] = Field(default_factory=dict)


class ReplayPage(BaseModel):
    """An oldest-first page anchored at a fixed upper timestamp."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    events: list[ReplayEvent]
    total: int
    offset: int
    next_offset: int | None
    as_of: datetime
    history_available: bool
    warnings: list[str] = Field(default_factory=list)


def research_replay(
    workspace: object,
    *,
    project_id: str | None = None,
    experiment_id: str | None = None,
    run_id: str | None = None,
    kind: str | None = None,
    offset: int = 0,
    limit: int = 100,
    as_of: datetime | None = None,
) -> ReplayPage:
    """Read research order within the served boundary, without reconciling/writing.

    Execution ids remain qualified by run. Equal timestamps retain lifecycle
    order; parallel attempts may overlap. A replay never executes any step.
    """
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("offset must be non-negative and limit must be between 1 and 200")
    if kind not in {None, "experiment", "run", "execution", "knowledge", "asset", "history"}:
        raise ValueError("unknown replay kind")
    until = as_of or datetime.now(UTC)
    if until.utcoffset() is None:
        raise ValueError("asOf needs a timezone")
    served = as_folder(workspace)
    scope = resolve_in_scope(served, project_id)
    for identifier, cls in [(experiment_id, Experiment), (run_id, Run)]:
        if identifier is None or identifier in {"", "-"}:
            continue
        matches = [node for node in descendants(scope, cls) if identifier in {node.id, node.name}]
        if len(matches) != 1:
            raise ValueError(
                f"{cls.__name__} {identifier!r} must identify one object in the served scope"
            )
        scope = matches[0]
    repo = Path(str(served.asset_host().resolve()))
    boundary = Path(str(scope.resolve()))
    serve_path = Path(str(served.resolve()))
    history = GitHistory(repo)
    available = isinstance(served.fs, LocalFS) and history.enabled()
    facts = history.entries() if available else []
    events: dict[str, ReplayEvent] = {}
    identities = {scope.metadata.id}
    # A history commit can be missing, but immutable attempt records still
    # establish creation/start/end. Never manufacture a start for a queued job.
    experiments = descendants(scope, Experiment)
    runs = descendants(scope, Run)
    nodes: list[tuple[Experiment | Run, Literal["experiment", "run"]]] = [
        *((e, "experiment") for e in experiments),
        *((r, "run") for r in runs),
    ]
    for node, node_kind in nodes:
        identities.add(node.id)
        reference = str(ref_of(node))
        key = f"{node.id}:{'ExperimentCreated' if node_kind == 'experiment' else 'RunDefined'}"
        events[key] = ReplayEvent(
            id=key,
            at=node.metadata.created_at,
            kind=node_kind,
            action=f"{node_kind}.created",
            title=node.name,
            ref=reference,
            details={"parameters": node.parameters} if isinstance(node, Run) else {},
        )
    for run in runs:
        reference = ref_of(run)
        for attempt in run.executions:
            subject = f"{run.id}:{attempt.id}"
            identities.add(subject)
            ref = str(
                MolabRef(
                    experiment_id=reference.experiment_id, run_id=run.id, execution_id=attempt.id
                )
            )
            details: dict[str, JSONValue] = {
                "runId": run.id,
                "executionId": attempt.id,
                "experimentId": reference.experiment_id,
                "experimentName": run.experiment.name,
                "parameters": run.parameters,
                "mode": attempt.mode.value,
                "basedOnExecutionId": attempt.based_on_execution_id,
            }
            for event, when, status in [
                ("ExecutionCreated", attempt.created_at, "created"),
                ("ExecutionStarted", attempt.started_at, "running"),
                ("ExecutionSealed", attempt.finished_at, attempt.status.value),
            ]:
                if when is None:
                    continue
                key = f"{subject}:{event}"
                events[key] = ReplayEvent(
                    id=key,
                    at=when,
                    kind="execution",
                    action=event,
                    title=f"{run.name} · {attempt.id} · {status}",
                    ref=ref,
                    actor=attempt.created_by,
                    details={
                        **details,
                        "status": status,
                        **({"error": attempt.error} if event == "ExecutionSealed" else {}),
                    },
                )
    hosts = {
        str(node.resolve()): node for node in [scope, *descendants(scope, Project), *experiments]
    }
    if isinstance(scope, Run) and Path(str(scope.experiment.resolve())).is_relative_to(serve_path):
        hosts[str(scope.experiment.resolve())] = scope.experiment
    for host in hosts.values():
        if not isinstance(host, (Workspace, Project, Experiment)):
            continue
        for asset in host.assets.list():
            if isinstance(scope, Run) and (
                not isinstance(asset.origin, ExecutionOrigin) or asset.origin.run_id != scope.id
            ):
                continue
            identities.add(asset.id)
            key = f"asset:{asset.id}:current"
            events[key] = ReplayEvent(
                id=key,
                at=asset.created_at,
                kind="asset",
                action="asset.current",
                title=asset.title,
                ref=str(ref_of(asset)),
                actor=asset.created_by,
                details={
                    "digest": asset.content.digest,
                    "origin": asset.origin.model_dump(mode="json"),
                    "currentVersion": True,
                },
            )
    for fact in reversed(facts):
        document = None
        if fact.event.startswith("knowledge."):
            candidate = repo / fact.subject.id
            if not candidate.is_relative_to(boundary):
                continue
            document = candidate.relative_to(serve_path).as_posix()
            if fact.subject.type == "Delegation" and fact.event != "knowledge.deleted":
                text = history.show(fact.commit, fact.subject.id)
                meta, _ = split_frontmatter(text or "", path=fact.subject.id)
                for field, action in [
                    ("decisions", "research.decision"),
                    ("approvals", "research.approved"),
                ]:
                    values = meta.get(field)
                    if not isinstance(values, list):
                        continue
                    for index, value in enumerate(values):
                        if not isinstance(value, dict) or not isinstance(value.get("at"), str):
                            continue
                        try:
                            when = datetime.fromisoformat(value["at"])
                        except ValueError:
                            continue
                        if when.utcoffset() is None:
                            continue
                        identity = f"{fact.subject.id}:{field}:{index}:{value['at']}"
                        if identity in events:
                            continue
                        reason = str(value.get("reason") or value.get("note") or "")
                        events[identity] = ReplayEvent(
                            id=identity,
                            at=when,
                            kind="knowledge",
                            action=action,
                            title=str(value.get("name") or f"Approved {value.get('gate', 'gate')}"),
                            actor=AgentRef(id=str(value["by"]), type="person")
                            if field == "approvals" and value.get("by")
                            else fact.agent,
                            commit=fact.commit,
                            document=document,
                            details={
                                "reason": reason,
                                "delegation": document,
                                "target": str(value.get("target") or ""),
                                "evidence": [
                                    item
                                    for item in value.get("evidence", [])
                                    if isinstance(item, str)
                                ]
                                if isinstance(value.get("evidence"), list)
                                else [],
                            },
                        )
        elif boundary != repo and not (
            fact.subject.id in identities
            or any(rel.object.id in identities for rel in fact.relations)
        ):
            continue
        key = f"{fact.subject.id}:{fact.event}"
        existing = events.get(key)
        if existing is not None:
            events[key] = existing.model_copy(update={"commit": fact.commit, "actor": fact.agent})
            continue
        # A historical document is opened at its commit, including after a
        # later rename/rewrite. Deleted versions remain on earlier events.
        events[f"git:{fact.commit}"] = ReplayEvent(
            id=f"git:{fact.commit}",
            at=fact.occurred_at,
            kind="knowledge" if document else "history",
            action=fact.event,
            title=fact.summary or fact.event,
            actor=fact.agent,
            commit=fact.commit,
            document=document if fact.event != "knowledge.deleted" else None,
            details={
                "subject": fact.subject.model_dump(),
                "relations": [rel.model_dump() for rel in fact.relations],
            },
        )
    # Dict insertion is deterministic and leaves queued → running → terminal
    # ordered when their recorded timestamps happen to be equal.
    ordered = sorted(
        (
            event
            for event in events.values()
            if event.at <= until and (kind is None or event.kind == kind)
        ),
        key=lambda event: event.at,
    )
    return ReplayPage(
        events=ordered[offset : offset + limit],
        total=len(ordered),
        offset=offset,
        next_offset=offset + limit if offset + limit < len(ordered) else None,
        as_of=until,
        history_available=available,
        warnings=[]
        if available
        else ["Historical document changes are unavailable; showing saved records."],
    )


def replay_document(workspace: object, commit: str, document: str) -> str:
    """Read a knowledge version actually recorded in this served scope's history."""
    served = as_folder(workspace)
    path = PurePosixPath(document)
    if (
        not re.fullmatch(r"[0-9a-f]{40,64}", commit)
        or path.is_absolute()
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[-2] != "knowledges"
        or not is_knowledge_file(document)
    ):
        raise ValueError("expected a recorded knowledge path and full commit id")
    if not isinstance(served.fs, LocalFS):
        raise LookupError("Historical document changes are unavailable")
    repo = Path(str(served.asset_host().resolve()))
    relative = (Path(str(served.resolve())) / str(path)).relative_to(repo).as_posix()
    history = GitHistory(repo)
    if not any(
        fact.commit == commit
        and fact.subject.id == relative
        and fact.event.startswith("knowledge.")
        for fact in history.entries(entity_id=relative)
    ):
        raise LookupError("Document version was not recorded in this scope")
    content = history.show(commit, relative)
    if content is None:
        raise LookupError("Document did not exist at that recorded version")
    return content


class DocumentHistory(BaseModel):
    """Git versions of one served knowledge file and an optional working-copy comparison."""

    available: bool
    revisions: list[FileRevision]
    commit: str | None = None
    body: str | None = None
    diff: str | None = None


def document_history(
    workspace: object, document: str, *, commit: str | None = None, limit: int = 50
) -> DocumentHistory:
    """Inspect file history, including manual commits, without changing Git or the file."""
    served = as_folder(workspace)
    path = PurePosixPath(document)
    if (
        path.is_absolute()
        or ".." in path.parts
        or len(path.parts) < 2
        or path.parts[-2] != "knowledges"
        or not is_knowledge_file(document)
        or (commit is not None and not re.fullmatch(r"[0-9a-f]{40,64}", commit))
        or not 1 <= limit <= 200
    ):
        raise ValueError("expected a served knowledge path, full commit id, and limit 1-200")
    if not isinstance(served.fs, LocalFS):
        return DocumentHistory(available=False, revisions=[])
    boundary = Path(str(served.resolve())).resolve()
    absolute = (boundary / str(path)).resolve()
    if not absolute.is_relative_to(boundary):
        raise ValueError("document must be inside the served scope")
    repo = Path(str(served.asset_host().resolve())).resolve()
    relative = absolute.relative_to(repo).as_posix()
    history = GitHistory(repo)
    revisions = history.file_revisions(relative, limit=limit)
    result = DocumentHistory(available=history.enabled(), revisions=revisions)
    if commit is None:
        return result
    if not any(revision.commit == commit for revision in revisions):
        raise LookupError("Version is not among this document's listed revisions")
    content = history.show(commit, relative)
    if content is None:
        raise LookupError("Document did not exist at that revision")
    current = absolute.read_text(encoding="utf-8") if absolute.is_file() else ""
    result.commit = commit
    result.body = content
    result.diff = "".join(
        unified_diff(
            content.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"{document}@{commit[:8]}",
            tofile=f"{document} (working copy)",
        )
    )
    return result
