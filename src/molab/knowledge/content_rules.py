"""Content rules for knowledge documents a person or another tool wrote by hand.

``write_knowledge`` refuses a malformed planning record or Delegation at write
time, but a document written straight to disk never passed that gate. These
rules read what is on disk and report, for :mod:`molab.knowledge.validate`:

* ``knowledge.record`` (error) — a Roadmap / Todo / Milestone / Delegation
  whose structured record its class rejects, or a Report / Note whose
  ``worker_report`` / ``brief`` record is invalid or on the wrong class.
* ``knowledge.campaign`` (error) — a Plan's campaign names a stage its roadmap
  does not have (:func:`~molab.knowledge.planning.check_campaign`).
* ``knowledge.uncited_planning`` (warning) — a Roadmap, Todo or Milestone that
  cites no Plan, so no campaign reads it.
* ``knowledge.stage_experiment`` (warning) — a roadmap stage names an
  experiment directory that does not exist.
* ``knowledge.local_source`` (warning) — a link to a local file outside the
  workspace, or to one that does not exist: the record is not portable.
* ``knowledge.literature_metadata`` (warning) — a Literature record with no DOI
  or URL, or no authors / year, in its frontmatter.
* ``knowledge.ephemeral_link`` (error) — a link to ``localhost`` / a loopback
  address: a port that served one session, dead for every later reader.
* ``knowledge.versioned_name`` (error) — a document named ``…-v2``. One
  subject is one document, rewritten in place; git keeps the old text.
* ``knowledge.report_unanchored`` (error) — a Report that cites no ``molab:``
  asset, run or execution, so nothing ties its claims to the bytes.

Read-only. ``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .record import COMMON_KEYS

if TYPE_CHECKING:
    from molab.fs import FileSystem

    from .concept import Concept

__all__ = ["CONTENT_RULE_HINTS", "ContentIssue", "content_issues"]

CONTENT_RULE_HINTS: dict[str, str] = {
    "knowledge.record": (
        "The document's structured fields do not validate for its class. Rewrite them "
        "with `molab knowledge write NAME --class CLASS --record '{...}'`."
    ),
    "knowledge.campaign": (
        "A Todo item or Milestone names a stage the Plan's Roadmap does not have. Add "
        "the stage to the Roadmap or correct the stage id."
    ),
    "knowledge.uncited_planning": (
        "Roadmap, Todo and Milestone documents belong to a campaign through a "
        "`[@derived_from …](plan.md)` link to its Plan. Add the link."
    ),
    "knowledge.stage_experiment": (
        "A roadmap stage's `experiment` is an experiment directory name. Create it "
        "with `molab experiment create`, or correct the name."
    ),
    "knowledge.local_source": (
        "Link a source inside the workspace: import data with `molab asset import`, "
        "cite papers by DOI or a Literature document. A path outside the workspace "
        "does not travel with it."
    ),
    "knowledge.literature_metadata": (
        "Put the bibliographic fields in frontmatter (title, authors, year, doi or "
        "url), e.g. `molab knowledge write NAME --class Literature --record '{...}'`."
    ),
    "knowledge.ephemeral_link": (
        "Cite the product by its `molab:asset/<id>` ref; molab's viewers render it. "
        "A localhost URL dies with the session that served it."
    ),
    "knowledge.versioned_name": (
        "Rewrite the document under its stable name (`molab knowledge write NAME …` "
        "replaces it; git keeps the old text) and delete the numbered copies."
    ),
    "knowledge.report_unanchored": (
        "Cite what the report is about: the `molab:asset/<id>` of each product it "
        "describes, or the run / execution ref that made them."
    ),
}

_EPHEMERAL_RE = re.compile(
    r"https?://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])(?::\d+)?", re.I
)
_VERSIONED_RE = re.compile(r"[-_ ]v\d+$", re.I)
_ANCHOR_RE = re.compile(r"molab:(?:asset/[0-9a-f-]+|experiment/[0-9a-z-]+/run/[0-9a-z-]+)")

_PLANNING_RECORD_ROLES = frozenset({"roadmap", "todo", "milestone"})


@dataclass(frozen=True)
class ContentIssue:
    """One finding: an absolute *path*, the rule, what is wrong, and how bad."""

    path: str
    rule: str
    detail: str
    severity: str


def _record(doc: Concept) -> dict[str, object]:
    return {key: value for key, value in doc.frontmatter().items() if key not in COMMON_KEYS}


def _record_issue(doc: Concept) -> ContentIssue | None:
    """``knowledge.record`` for a document whose class, or whose ``kind``, owns a record."""
    from .planning import check_planning_record
    from .worker_report import WORKER_RECORD_CLASSES, check_worker_record

    klass = type(doc)
    role = getattr(klass, "PLANNING_ROLE", None)
    check_record = getattr(klass, "check_record", None)
    payload = _record(doc)
    kind = payload.get("kind")
    worker = isinstance(kind, str) and kind in WORKER_RECORD_CLASSES
    if role not in _PLANNING_RECORD_ROLES and check_record is None and not worker:
        return None
    if role == "milestone":
        # A milestone's lifecycle status is its record's status.
        payload["status"] = doc.frontmatter().get("status", "open")
    try:
        if check_record is not None:
            check_record(payload, existing=None)
        check_planning_record(klass, payload, creating=True)
        check_worker_record(klass, payload, existing=None)
    except (ValueError, TypeError) as exc:
        return ContentIssue(str(doc.path), "knowledge.record", str(exc), "error")
    return None


def _is_local(target: str) -> bool:
    from molab.workspace.refs import is_ref

    return not (
        target.startswith(("#", "http://", "https://", "mailto:"))
        or "://" in target
        or is_ref(target)
    )


def _source_issues(doc: Concept, root: str, fs: FileSystem) -> Iterator[ContentIssue]:
    """``knowledge.local_source`` for each local link that leaves the root or is missing."""
    prefix = root.rstrip("/") + "/"
    for edge in doc.links():
        target = edge.target.split("#", 1)[0]
        if target == "" or not _is_local(target):
            continue
        # links() already resolved the target against the document's directory.
        resolved = posixpath.normpath(posixpath.abspath(target))
        if not (resolved == root or resolved.startswith(prefix)):
            yield ContentIssue(
                str(doc.path),
                "knowledge.local_source",
                f"@{edge.role} link {edge.target!r} points outside the workspace ({resolved})",
                "warning",
            )
        elif not fs.exists(resolved):
            yield ContentIssue(
                str(doc.path),
                "knowledge.local_source",
                f"@{edge.role} link {edge.target!r} names a file that does not exist",
                "warning",
            )


def _literature_issue(doc: Concept) -> ContentIssue | None:
    meta = doc.frontmatter()
    missing = [field for field in ("authors", "year") if not meta.get(field)]
    if not (meta.get("doi") or meta.get("url")):
        missing.insert(0, "doi or url")
    if not missing:
        return None
    return ContentIssue(
        str(doc.path),
        "knowledge.literature_metadata",
        f"frontmatter has no {', '.join(missing)}; the citation lives only in prose",
        "warning",
    )


def _ephemeral_issue(doc: Concept) -> ContentIssue | None:
    found = _EPHEMERAL_RE.search(doc.read())
    if found is None:
        return None
    return ContentIssue(
        str(doc.path),
        "knowledge.ephemeral_link",
        f"links {found.group(0)!r}, a session-local server",
        "error",
    )


def _versioned_issue(doc: Concept) -> ContentIssue | None:
    stem = posixpath.splitext(posixpath.basename(str(doc.path)))[0]
    if _VERSIONED_RE.search(stem) is None:
        return None
    return ContentIssue(
        str(doc.path),
        "knowledge.versioned_name",
        f"{stem!r} carries a version number; one subject is one document",
        "error",
    )


def _anchor_issue(doc: Concept) -> ContentIssue | None:
    from .concepts import Report

    if not isinstance(doc, Report) or _ANCHOR_RE.search(doc.read()):
        return None
    return ContentIssue(
        str(doc.path),
        "knowledge.report_unanchored",
        "the report cites no molab: asset, run or execution",
        "error",
    )


def _experiment_names(root: str, fs: FileSystem) -> frozenset[str]:
    from molab.workspace import Workspace
    from molab.workspace.naming import EXPERIMENT_CONTAINER

    names = set()
    for host in Workspace.list_hosts(root, fs=fs):
        parent, name = posixpath.split(str(host))
        if posixpath.basename(parent) == EXPERIMENT_CONTAINER:
            names.add(name)
    if (
        Workspace.is_node_dir(root, fs=fs)
        and posixpath.basename(posixpath.dirname(root)) == EXPERIMENT_CONTAINER
    ):
        names.add(posixpath.basename(root))
    return frozenset(names)


def _campaign_issues(docs: list[Concept], root: str, fs: FileSystem) -> Iterator[ContentIssue]:
    """``knowledge.campaign``, ``knowledge.uncited_planning``, ``knowledge.stage_experiment``."""
    from .concepts import Plan, Roadmap
    from .planning import campaign_of, check_campaign

    members: set[str] = set()
    experiments: frozenset[str] | None = None
    for plan in (doc for doc in docs if type(doc) is Plan):
        try:
            campaign = campaign_of(plan)
        except (OSError, ValueError) as exc:
            yield ContentIssue(str(plan.path), "knowledge.campaign", str(exc), "error")
            continue
        members.update(
            str(getattr(item, "path", ""))
            for item in (*campaign.roadmaps, *campaign.todos, *campaign.milestones)
        )
        try:
            check_campaign(campaign)
        except ValueError as exc:
            yield ContentIssue(str(plan.path), "knowledge.campaign", str(exc), "error")
        for roadmap in (item for item in campaign.roadmaps if isinstance(item, Roadmap)):
            experiments = experiments if experiments is not None else _experiment_names(root, fs)
            try:
                stages = roadmap.stages()
            except ValueError:
                continue  # knowledge.record reports it
            for stage in stages:
                name = getattr(stage, "experiment", None)
                if name and name not in experiments:
                    yield ContentIssue(
                        str(roadmap.path),
                        "knowledge.stage_experiment",
                        f"stage {getattr(stage, 'id', '?')!r} names experiment {name!r}, which does not exist",
                        "warning",
                    )
    for doc in docs:
        if (
            getattr(type(doc), "PLANNING_ROLE", None) in _PLANNING_RECORD_ROLES
            and str(doc.path) not in members
        ):
            yield ContentIssue(
                str(doc.path),
                "knowledge.uncited_planning",
                f"this {type(doc).__name__} cites no Plan, so no campaign reads it",
                "warning",
            )


def content_issues(
    paths: Iterable[str],
    *,
    root: str,
    fs: FileSystem,
    errors_only: bool = False,
) -> list[ContentIssue]:
    """Every content finding for the documents at *paths* (absolute, class already valid).

    Args:
        paths: Document files to check.
        root: The workspace (or served node) directory the documents live under.
        fs: The disk to read.
        errors_only: Skip the rules that can only warn.
    """
    from .concepts import Literature, _open_document
    from .errors import KnowledgeNotFoundError

    docs: list[Concept] = []
    for path in paths:
        try:
            docs.append(_open_document(path, fs=fs))
        except (KnowledgeNotFoundError, OSError, ValueError):
            continue
    found: list[ContentIssue] = []
    for doc in docs:
        for check in (_record_issue, _ephemeral_issue, _versioned_issue, _anchor_issue):
            issue = check(doc)
            if issue is not None:
                found.append(issue)
    found.extend(
        issue
        for issue in _campaign_issues(docs, root, fs)
        if not (errors_only and issue.severity == "warning")
    )
    if errors_only:
        return found
    for doc in docs:
        found.extend(_source_issues(doc, root, fs))
        if isinstance(doc, Literature):
            literature = _literature_issue(doc)
            if literature is not None:
                found.append(literature)
    return found
