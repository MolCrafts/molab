"""Content rules for knowledge documents a person or another tool wrote by hand.

``write_knowledge`` refuses a malformed structured record at write time, but a
document written straight to disk never passed that gate. These rules read what
is on disk and report, for :mod:`molab.knowledge.validate`:

* ``knowledge.fields`` (error) — a frontmatter key the document's class does
  not declare, or a value it rejects (a Hypothesis ``verdict`` outside the
  vocabulary).
* ``knowledge.local_source`` (warning) — a link to a local file outside the
  workspace, or to one that does not exist: the record is not portable.
* ``knowledge.literature_metadata`` (warning) — a Literature record with no DOI
  or URL, or no authors / year, in its frontmatter.
* ``knowledge.ephemeral_link`` (error) — a link to ``localhost`` / a loopback
  address: a port that served one session, dead for every later reader.
* ``knowledge.versioned_name`` (error) — a document named ``…-v2``. One
  subject is one document, rewritten in place; git keeps the old text.
* ``knowledge.unanchored`` (error) — a Report or Finding that cites no
  ``molab:`` asset, run or execution, so nothing ties its claims to the bytes.
  :func:`unanchored` is the rule; :meth:`Concept.write` refuses such a write.

``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .fields import check_fields, own_fields

if TYPE_CHECKING:
    from molab.fs import FileSystem

    from .concept import Concept

__all__ = ["CONTENT_RULE_HINTS", "ContentIssue", "content_issues"]

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
    "knowledge.unanchored": (
        "Cite what the report or finding rests on: the `molab:asset/<id>` of each "
        "product it describes, or the run / execution ref that made them."
    ),
}

_EPHEMERAL_RE = re.compile(
    r"https?://(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|\[::1\])(?::\d+)?", re.I
)
_VERSIONED_RE = re.compile(r"[-_ ]v\d+$", re.I)
#: The ref kinds that tie a claim to registered bytes.
_ANCHOR_KINDS = frozenset({"asset", "run", "execution"})


@dataclass(frozen=True)
class ContentIssue:
    """One finding: an absolute *path*, the rule, what is wrong, and how bad."""

    path: str
    rule: str
    detail: str
    severity: str


def _fields_issue(doc: Concept) -> ContentIssue | None:
    """``knowledge.fields`` for a frontmatter the document's class refuses."""
    try:
        check_fields(type(doc), own_fields(doc.frontmatter()))
    except ValueError as exc:
        return ContentIssue(str(doc.path), "knowledge.fields", str(exc), "error")
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


def _anchor_issue(doc: Concept) -> ContentIssue | None:
    problem = unanchored(type(doc), doc.read())
    if problem is None:
        return None
    return ContentIssue(str(doc.path), "knowledge.unanchored", problem, "error")


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
        for check in (_fields_issue, _ephemeral_issue, _versioned_issue, _anchor_issue):
            issue = check(doc)
            if issue is not None:
                found.append(issue)
    if errors_only:
        return found
    for doc in docs:
        found.extend(_source_issues(doc, root, fs))
        if isinstance(doc, Literature):
            literature = _literature_issue(doc)
            if literature is not None:
                found.append(literature)
    return found
