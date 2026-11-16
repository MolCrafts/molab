"""Content rules for knowledge documents.

The error rules are one function, :func:`error_issues`. :mod:`molab.knowledge.validate`
reports them for a document on disk (one a person or another tool wrote
straight to disk never passed the write gate), and
:meth:`~molab.knowledge.concept.Concept.write` refuses a write that would leave
one (:class:`ContentRuleError`). The rules:

* ``knowledge.fields`` (error) — a frontmatter key the document's class does
  not declare, or a value it rejects (a Hypothesis ``verdict`` outside the
  vocabulary).
* ``knowledge.local_source`` (warning) — a link to a local file outside the
  workspace, or to one that does not exist: the record is not portable.
* ``knowledge.literature_metadata`` (warning) — a Literature record with no DOI
  or URL, or no authors / year, in its frontmatter.
* ``knowledge.ephemeral_link`` (error) — a link to ``localhost`` / a loopback
  address outside code: a port that served one session, dead for every later
  reader.
* ``knowledge.versioned_name`` (error) — a document named ``…-v2``. One
  subject is one document, rewritten in place; git keeps the old text.
* ``knowledge.html_page`` (error) — a markdown document holding page markup
  (``<!doctype``, ``<html>``, ``<head>``, ``<body>``, ``<iframe>``,
  ``<script>`` or ``<style>``) outside code. The body is Markdown that molab
  renders; an ``.html`` document is the one meant to be a page.
* ``knowledge.unanchored`` (error) — a Report or Finding that cites no
  ``molab:`` asset, run or execution, so nothing ties its claims to the bytes.
* ``knowledge.stage`` (error) — a Todo item or a Milestone names a stage that
  no Roadmap citing the same Plan has. A document that cites no Plan belongs
  to no plan's order and is not checked. This is the one rule that reads more
  than one document, so a write is not refused for it (writing the Todo before
  its Roadmap is legal); ``molab validate`` and the end-of-session check report it.

The rules below also read more than the document, so they too are reported
and never refuse a write:

* ``knowledge.milestone_evidence`` (error) — a Milestone's status rests on
  nothing: a measurement that no longer agrees with the asset it cites (the
  ref names nothing, the bytes are no longer its run's own as
  ``evaluate_milestone`` requires, they changed, or they hold another value
  at the span), or a ``met`` / ``missed`` Milestone with no checks that
  neither links a Finding nor is linked by one.
* ``knowledge.stage_order`` (error) — a ``met`` Milestone closes a stage while
  a Milestone of a stage it depends on is not ``met``.
* ``knowledge.verdict_evidence`` (error) — a Hypothesis is ``supported`` with
  no Finding that links it as ``supports``, or ``refuted`` with none that
  links it as ``contradicts``.
* ``knowledge.dangling_ref`` (error) — a Report or Finding links a ``molab:``
  ref that names nothing in the workspace.
* ``knowledge.citation`` (error) — a Manuscript ``\\cite``s a key that no
  Literature document in its host or a host above it is named.
* ``knowledge.source_text`` (warning) — a Literature that a Plan links points
  at no PDF, or at one that is not there: the Plan cannot be checked against
  the text it reproduces.

``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .fields import check_fields, own_fields

if TYPE_CHECKING:
    from molab.fs import FileSystem
    from molab.workspace import Workspace

    from .concept import Concept

    #: Every document of the workspace, read at most once per report.
    type _Walk = Callable[[], Sequence[Concept]]

__all__ = [
    "CONTENT_RULE_HINTS",
    "ContentIssue",
    "ContentRuleError",
    "content_issues",
    "error_issues",
]

CONTENT_RULE_HINTS: dict[str, str] = {
    "knowledge.fields": (
        "The frontmatter holds a key its class does not declare, or a value the class "
        "refuses. Rewrite the fields with `molab knowledge write NAME --class CLASS "
        "--fields '{...}'`, or replace them whole with PATCH /api/knowledge/doc/fields."
    ),
    "knowledge.local_source": (
        "Link a source inside the workspace: import data with `molab asset import`, "
        "cite papers by DOI or a Literature document. A path outside the workspace "
        "does not travel with it."
    ),
    "knowledge.literature_metadata": (
        "Put the bibliographic fields in frontmatter (title, authors, year, doi or "
        "url), e.g. `molab knowledge write NAME --class Literature --fields '{...}'`."
    ),
    "knowledge.ephemeral_link": (
        "Cite the product by its `molab:asset/<id>` ref; molab's viewers render it. "
        "A localhost URL dies with the session that served it."
    ),
    "knowledge.versioned_name": (
        "Rewrite the document under its stable name (`molab knowledge write NAME …` "
        "replaces it; git keeps the old text) and delete the numbered copies."
    ),
    "knowledge.html_page": (
        "Write the body as Markdown: molab renders it, and a `molab:asset/<id>` ref "
        "shows a figure or a structure. A standalone page is an `.html` document "
        "(`--format html`)."
    ),
    "knowledge.unanchored": (
        "Cite what the report or finding rests on: the `molab:asset/<id>` of each "
        "product it describes, or the run / execution ref that made them."
    ),
    "knowledge.stage": (
        "Name a stage the Roadmap of the same Plan declares, or add the stage to that "
        "Roadmap (`molab knowledge write NAME --class Roadmap --fields '{\"stages\": [...]}'`)."
    ),
    "knowledge.milestone_evidence": (
        "Measure the checks from a run's registered files with `molab knowledge evaluate "
        "DOC --measure CHECK=molab:asset/<id>`. A Milestone with no checks links the "
        "Finding that settles it."
    ),
    "knowledge.stage_order": (
        "Settle the Milestones of the stages this one depends on first, or set this "
        "Milestone back to open."
    ),
    "knowledge.verdict_evidence": (
        "Link the Hypothesis from the Finding that settles it, with role `supports` "
        "or `contradicts`, or set the verdict to `open` / `unsettled`."
    ),
    "knowledge.source_text": (
        "Import the paper and point the Literature at it: `molab asset import paper.pdf "
        "-p PROJECT`, then set `pdf_asset_id` in its fields. A Plan is checked against "
        "the text of what it reproduces."
    ),
    "knowledge.citation": (
        "Cite a work by the name of its Literature document (`\\cite{<name>}`), or write "
        "that Literature first: `molab knowledge write NAME --class Literature --fields "
        '\'{"title": ..., "authors": [...], "year": ..., "doi": ...}\'`.'
    ),
    "knowledge.dangling_ref": (
        "Cite a ref that exists: `molab index show --frontmatter` lists the runs, and "
        "`molab asset list` the assets."
    ),
}

_EPHEMERAL_RE = re.compile(
    r"https?://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])(?::\d+)?", re.I
)
_VERSIONED_RE = re.compile(r"[-_ ]v\d+$", re.I)
_HTML_PAGE_RE = re.compile(r"<\s*(?:!doctype|html|head|body|iframe|script|style)\b", re.I)
#: The role a Finding links a Hypothesis with to back each settled verdict.
_VERDICT_ROLES = {"supported": "supports", "refuted": "contradicts"}
#: The ref kinds that tie a claim to registered bytes.
_ANCHOR_KINDS = frozenset({"asset", "run", "execution"})


@dataclass(frozen=True)
class ContentIssue:
    """One finding: an absolute *path*, the rule, what is wrong, and how bad."""

    path: str
    rule: str
    detail: str
    severity: str


class ContentRuleError(ValueError):
    """A write refused: the document it would leave breaks an error-level rule.

    The message names each rule and the offending text.

    Attributes:
        issues: The rules the document would break.
    """

    def __init__(self, issues: Sequence[ContentIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{issue.rule}: {issue.detail}" for issue in self.issues))


def error_issues(
    klass: type[Concept], path: str, meta: Mapping[str, object], body: str
) -> list[ContentIssue]:
    """The error findings for a *klass* document at *path* holding *meta* and *body*.

    The one definition of what a document may not hold: validate reports these
    for a file on disk, and a write that would leave one is refused.
    """
    from .concept import _mask_code
    from .naming import is_html_document

    found: list[ContentIssue] = []
    try:
        check_fields(klass, own_fields(meta))
    except ValueError as exc:
        # The frontmatter is outside data: pydantic's refusal is the finding.
        found.append(ContentIssue(path, "knowledge.fields", str(exc), "error"))
    prose = _mask_code(body)
    link = _EPHEMERAL_RE.search(prose)
    if link is not None:
        found.append(
            ContentIssue(
                path,
                "knowledge.ephemeral_link",
                f"links {link.group(0)!r}, a session-local server",
                "error",
            )
        )
    stem = posixpath.splitext(posixpath.basename(path))[0]
    if _VERSIONED_RE.search(stem) is not None:
        found.append(
            ContentIssue(
                path,
                "knowledge.versioned_name",
                f"{stem!r} carries a version number; one subject is one document",
                "error",
            )
        )
    page = None if is_html_document(path) else _HTML_PAGE_RE.search(prose)
    if page is not None:
        found.append(
            ContentIssue(
                path,
                "knowledge.html_page",
                f"holds {page.group(0)!r}: a markdown document is not an HTML page",
                "error",
            )
        )
    problem = unanchored(klass, body)
    if problem is not None:
        found.append(ContentIssue(path, "knowledge.unanchored", problem, "error"))
    return found


def refuse_errors(klass: type[Concept], path: str, meta: Mapping[str, object], body: str) -> None:
    """Refuse a write that would leave a document :func:`error_issues` reports.

    Raises:
        ContentRuleError: Naming every rule the document would break.
    """
    issues = error_issues(klass, path, meta, body)
    if issues:
        raise ContentRuleError(issues)


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


def _is_anchor(target: str) -> bool:
    """Whether a link *target* is a well-formed asset, run or execution ref."""
    from molab.workspace.refs import InvalidRefError, is_ref, parse_ref

    ref = target.split("#", 1)[0]
    if not is_ref(ref):
        return False
    try:
        return parse_ref(ref).kind in _ANCHOR_KINDS
    except InvalidRefError:
        # A document's text is outside data: a malformed ref anchors nothing.
        return False


def unanchored(klass: type[Concept], body: str) -> str | None:
    """Why a *klass* document whose narrative is *body* rests on nothing, or ``None``.

    A Report or Finding (or a subclass) must link a ``molab:`` asset, run or
    execution; every other class answers ``None``.
    """
    from .concept import markdown_links
    from .concepts import Finding, Report

    if not issubclass(klass, (Report, Finding)):
        return None
    if any(_is_anchor(link.group(2)) for link in markdown_links(body)):
        return None
    return f"a {klass.__name__} cites no molab: asset, run or execution"


def _named_stages(doc: Concept) -> list[str]:
    """The Roadmap stages a Todo's items or a Milestone name; ``[]`` for any other class.

    *doc*'s fields already passed its class's model.
    """
    from .concepts import Milestone, Todo

    if isinstance(doc, Todo):
        return [item.stage for item in doc.fields().items if item.stage is not None]
    if isinstance(doc, Milestone):
        stage = doc.fields().stage
        return [] if stage is None else [stage]
    return []


def _local_targets(doc: Concept) -> set[str]:
    """The normalized local files *doc* links, whatever the role."""
    found: set[str] = set()
    for edge in doc.links():
        target = edge.target.split("#", 1)[0]
        if target and _is_local(target):
            # links() already resolved the target against the document's directory.
            found.add(posixpath.normpath(target))
    return found


def _stage_issues(docs: Sequence[Concept], everything: _Walk) -> Iterator[ContentIssue]:
    """``knowledge.stage`` for each stage a Todo item or Milestone names that its Plan lacks.

    The Plans a document cites are the Plan documents it links. Their stages
    are those of every Roadmap anywhere under *root* that links the same
    Plan. A document that links no Plan is not checked.
    """
    named = [(doc, stages) for doc in docs if (stages := _named_stages(doc))]
    if not named:
        return
    from .concepts import Plan, Roadmap

    walked = everything()
    plans = {posixpath.normpath(str(doc.path)) for doc in walked if isinstance(doc, Plan)}
    staged: dict[str, set[str]] = {plan: set() for plan in plans}
    for roadmap in (doc for doc in walked if isinstance(doc, Roadmap)):
        try:
            ids = {stage.id for stage in roadmap.fields().stages}
        except ValueError:
            # The frontmatter is outside data: knowledge.fields reports a refused one.
            continue
        for plan in _local_targets(roadmap) & plans:
            staged[plan] |= ids
    for doc, stages in named:
        cited = _local_targets(doc) & plans
        if not cited:
            continue
        known = set().union(*(staged[plan] for plan in cited))
        for stage in stages:
            if stage not in known:
                yield ContentIssue(
                    str(doc.path),
                    "knowledge.stage",
                    f"names stage {stage!r}, which no Roadmap citing its Plan declares",
                    "error",
                )


def _milestone_stage_issues(
    milestones: Sequence[Concept], everything: Sequence[Concept]
) -> Iterator[ContentIssue]:
    """``knowledge.stage_order`` for each met Milestone ahead of a stage it depends on.

    The order is the Roadmap's that cites the Milestone's Plan. A dependency
    that no Milestone of that Plan names is not checked.
    """
    from .concepts import Milestone, Plan, Roadmap

    plans = {posixpath.normpath(str(doc.path)) for doc in everything if isinstance(doc, Plan)}
    depends: dict[str, dict[str, tuple[str, ...]]] = {plan: {} for plan in plans}
    for roadmap in (doc for doc in everything if isinstance(doc, Roadmap)):
        try:
            stages = {stage.id: stage.depends_on for stage in roadmap.fields().stages}
        except ValueError:
            continue
        for plan in _local_targets(roadmap) & plans:
            depends[plan].update(stages)
    closing: dict[tuple[str, str], list[Milestone]] = {}
    for doc in (doc for doc in everything if isinstance(doc, Milestone)):
        try:
            stage = doc.fields().stage
        except ValueError:
            continue
        if stage is None:
            continue
        for plan in _local_targets(doc) & plans:
            closing.setdefault((plan, stage), []).append(doc)
    for doc in milestones:
        assert isinstance(doc, Milestone)
        fields = doc.fields()
        if fields.status != "met" or fields.stage is None:
            continue
        for plan in sorted(_local_targets(doc) & plans):
            for needed in depends[plan].get(fields.stage, ()):
                behind = [
                    other.name
                    for other in closing.get((plan, needed), [])
                    if other.fields().status != "met"
                ]
                if behind:
                    yield ContentIssue(
                        str(doc.path),
                        "knowledge.stage_order",
                        f"is met, but stage {needed!r}, which {fields.stage!r} depends on, "
                        f"is not: {', '.join(sorted(behind))}",
                        "error",
                    )


def _evidence_issues(docs: Sequence[Concept], walk: _Walk) -> Iterator[ContentIssue]:
    """The rules that hold a settled status to the documents and bytes behind it."""
    from .acceptance import evidence_problems
    from .concepts import Finding, Hypothesis, Milestone

    judged = [doc for doc in docs if isinstance(doc, (Milestone, Hypothesis))]
    if not judged:
        return
    everything = walk()
    #: Finding path -> {(target path, role)}: who a Finding links, and how.
    findings = {
        posixpath.normpath(str(doc.path)): {
            (posixpath.normpath(edge.target.split("#", 1)[0]), edge.role) for edge in doc.links()
        }
        for doc in everything
        if isinstance(doc, Finding)
    }

    def linked_by_finding(path: str, roles: frozenset[str] | None = None) -> bool:
        return any(
            target == path and (roles is None or role in roles)
            for edges in findings.values()
            for target, role in edges
        )

    milestones = [doc for doc in judged if isinstance(doc, Milestone)]
    for doc in milestones:
        fields = doc.fields()
        path = posixpath.normpath(str(doc.path))
        for problem in evidence_problems(doc):
            yield ContentIssue(str(doc.path), "knowledge.milestone_evidence", problem, "error")
        if fields.checks or fields.status == "open":
            continue
        if not (_local_targets(doc) & set(findings) or linked_by_finding(path)):
            yield ContentIssue(
                str(doc.path),
                "knowledge.milestone_evidence",
                f"is {fields.status} with no checks and no Finding that settles it",
                "error",
            )
    yield from _milestone_stage_issues(milestones, everything)
    for doc in (doc for doc in judged if isinstance(doc, Hypothesis)):
        role = _VERDICT_ROLES.get(doc.fields().verdict)
        if role is None:
            continue
        if not linked_by_finding(posixpath.normpath(str(doc.path)), frozenset({role})):
            yield ContentIssue(
                str(doc.path),
                "knowledge.verdict_evidence",
                f"is {doc.fields().verdict} with no Finding that links it as @{role}",
                "error",
            )


def _dangling_issues(docs: Sequence[Concept], root: str, fs: FileSystem) -> Iterator[ContentIssue]:
    """``knowledge.dangling_ref`` for each ref a Report or Finding links that names nothing.

    The asset stores are read once for the whole report. A ref whose lookup
    cannot be finished (an unmigrated store, a record that does not read, an
    id in two scopes) is not reported here: the workspace rules report why.
    """
    from .concepts import Finding, Report

    anchored = [doc for doc in docs if isinstance(doc, (Report, Finding))]
    if not anchored:
        return
    from molab.workspace import Workspace
    from molab.workspace.errors import RefNotFoundError
    from molab.workspace.refs import InvalidRefError, parse_ref

    workspace = Workspace(root, fs=fs)
    asset_ids: frozenset[str] | None = None
    scanned = False
    known: dict[str, bool] = {}
    for doc in anchored:
        for edge in doc.links():
            ref = edge.target.split("#", 1)[0]
            if not edge.is_ref:
                continue
            if ref not in known:
                try:
                    parsed = parse_ref(ref)
                    if parsed.asset_id is not None:
                        if not scanned:
                            asset_ids, scanned = _asset_ids(workspace), True
                        known[ref] = asset_ids is None or parsed.asset_id in asset_ids
                    else:
                        workspace.find(parsed)
                        known[ref] = True
                except (RefNotFoundError, InvalidRefError):
                    known[ref] = False
                except (LookupError, RuntimeError, ValueError, OSError):
                    known[ref] = True
            if not known[ref]:
                yield ContentIssue(
                    str(doc.path),
                    "knowledge.dangling_ref",
                    f"links {ref}, which names nothing in this workspace",
                    "error",
                )


def _citation_issues(docs: Sequence[Concept]) -> Iterator[ContentIssue]:
    """``knowledge.citation`` for each Manuscript key no Literature document answers."""
    from .concepts import Manuscript

    for doc in docs:
        if not isinstance(doc, Manuscript):
            continue
        unknown = [key for key, found in doc.citations() if found is None]
        if unknown:
            yield ContentIssue(
                str(doc.path),
                "knowledge.citation",
                f"\\cite key(s) {', '.join(unknown)} name no Literature document",
                "error",
            )


def _asset_ids(workspace: Workspace) -> frozenset[str] | None:
    """The id of every asset in *workspace*; ``None`` when a store cannot be listed."""
    from molab.workspace.asset_repository import scan_asset_repositories

    try:
        return frozenset(
            asset.id
            for repository in scan_asset_repositories(workspace)
            for asset in repository.list()
        )
    except (RuntimeError, ValueError, OSError):
        return None


def _source_text_issues(
    docs: Sequence[Concept], root: str, fs: FileSystem
) -> Iterator[ContentIssue]:
    """``knowledge.source_text`` for each Literature a Plan links whose text is not at hand.

    The text is the asset ``pdf_asset_id`` names, or the file at ``pdf_path``.
    """
    from .concepts import Literature, Plan

    cited = {target for doc in docs if isinstance(doc, Plan) for target in _local_targets(doc)}
    papers = [
        doc
        for doc in docs
        if isinstance(doc, Literature) and posixpath.normpath(str(doc.path)) in cited
    ]
    if not papers:
        return
    from molab.workspace import Workspace
    from molab.workspace.errors import RefNotFoundError
    from molab.workspace.refs import MolabRef

    workspace = Workspace(root, fs=fs)
    for doc in papers:
        try:
            fields = doc.fields()
        except ValueError:
            continue
        problem: str | None = None
        if fields.pdf_asset_id is not None:
            try:
                workspace.find(MolabRef(asset_id=fields.pdf_asset_id))
            except (RefNotFoundError, ValueError):
                # ValueError: the field does not hold an asset id at all.
                problem = f"pdf_asset_id {fields.pdf_asset_id!r} names no asset in this workspace"
            except (LookupError, RuntimeError, OSError):
                # The store cannot be searched; the workspace rules report why.
                problem = None
        elif fields.pdf_path is not None:
            located = posixpath.join(posixpath.dirname(str(doc.path)), fields.pdf_path)
            if not fs.exists(located):
                problem = f"pdf_path {fields.pdf_path!r} names a file that does not exist"
        else:
            problem = "a Plan cites it, but it points at no PDF (pdf_asset_id or pdf_path)"
        if problem is not None:
            yield ContentIssue(str(doc.path), "knowledge.source_text", problem, "warning")


def _walk_once(root: str, fs: FileSystem) -> _Walk:
    """Every document under *root*, walked on the first call and kept for the rest."""
    walked: list[Concept] = []

    def walk() -> Sequence[Concept]:
        if not walked:
            from .concept import Knowledge

            walked.extend(Knowledge(root, fs=fs).walk())
        return walked

    return walk


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
        found.extend(error_issues(type(doc), str(doc.path), doc.frontmatter(), doc.read()))
    refused = {issue.path for issue in found if issue.rule == "knowledge.fields"}
    sound = [doc for doc in docs if str(doc.path) not in refused]
    walk = _walk_once(root, fs)
    found.extend(_stage_issues(sound, walk))
    found.extend(_evidence_issues(sound, walk))
    found.extend(_dangling_issues(sound, root, fs))
    found.extend(_citation_issues(sound))
    if errors_only:
        return found
    found.extend(_source_text_issues(sound, root, fs))
    for doc in docs:
        found.extend(_source_issues(doc, root, fs))
        if isinstance(doc, Literature):
            literature = _literature_issue(doc)
            if literature is not None:
                found.append(literature)
    return found
