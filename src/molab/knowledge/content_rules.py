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

``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .fields import check_fields, own_fields

if TYPE_CHECKING:
    from molab.fs import FileSystem

    from .concept import Concept

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
}

_EPHEMERAL_RE = re.compile(
    r"https?://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])(?::\d+)?", re.I
)
_VERSIONED_RE = re.compile(r"[-_ ]v\d+$", re.I)
_HTML_PAGE_RE = re.compile(r"<\s*(?:!doctype|html|head|body|iframe|script|style)\b", re.I)
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


def _stage_issues(docs: Sequence[Concept], root: str, fs: FileSystem) -> Iterator[ContentIssue]:
    """``knowledge.stage`` for each stage a Todo item or Milestone names that its Plan lacks.

    The Plans a document cites are the Plan documents it links. Their stages
    are those of every Roadmap anywhere under *root* that links the same
    Plan. A document that links no Plan is not checked.
    """
    named = [(doc, stages) for doc in docs if (stages := _named_stages(doc))]
    if not named:
        return
    from .concept import Knowledge
    from .concepts import Plan, Roadmap

    everything = list(Knowledge(root, fs=fs).walk())
    plans = {posixpath.normpath(str(doc.path)) for doc in everything if isinstance(doc, Plan)}
    staged: dict[str, set[str]] = {plan: set() for plan in plans}
    for roadmap in (doc for doc in everything if isinstance(doc, Roadmap)):
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
    found.extend(_stage_issues([doc for doc in docs if str(doc.path) not in refused], root, fs))
    if errors_only:
        return found
    for doc in docs:
        found.extend(_source_issues(doc, root, fs))
        if isinstance(doc, Literature):
            literature = _literature_issue(doc)
            if literature is not None:
                found.append(literature)
    return found
