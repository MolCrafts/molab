"""Validate the knowledge documents of a workspace. Read-only.

The workspace validator holds the tree to the layout law and does not know
``knowledges/`` (a layer above it declares that container). This module
checks what lives inside it, at every host (the root, each project,
experiment and run):

* ``knowledge.class`` (error) — a document whose record has no ``class:``
  or names a class that is not a knowledge class.
* ``knowledge.stray`` (error) — an entry of ``knowledges/`` that is not a
  document (``.md`` / ``.html``) or the ``figs/`` figure directory.
* ``knowledge.duplicate`` (error) — two documents with one stem (``a.md``
  beside ``a.html``): one name, one file.
* the content rules of :mod:`molab.knowledge.content_rules` — malformed
  records, campaign gaps, uncited planning documents, missing experiments,
  links that leave the workspace, Literature without bibliographic fields.
* ``knowledge.section_drift`` (warning) — the host's ``index.knowledges``
  section differs from a rebuild from the files. Like the derived ``index:``
  keys it is navigation sugar: a legal direct write of a document leaves it
  stale, and ``molab index sync`` rebuilds it.

Issues are plain dicts shaped like the workspace report's violations
(``path`` / ``rule`` / ``detail`` / ``severity`` / ``hint``), so the service
that composes both reports needs no knowledge types.

``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from molab.fs import FileSystem, LocalFS, PathArg

from .content_rules import CONTENT_RULE_HINTS, content_issues
from .naming import KNOWLEDGE_CONTAINER, KNOWLEDGE_MEDIA_DIR, is_knowledge_file, knowledge_stem

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = [
    "RULE_HINTS",
    "classify_document",
    "duplicate_documents",
    "known_classes",
    "validate_knowledge",
]

#: Stable rule id -> remediation hint naming the molab command to use.
RULE_HINTS: dict[str, str] = {
    "knowledge.class": (
        "A knowledge document names its class in frontmatter. Write it with "
        "`molab knowledge write NAME TEXT --on HOST --class CLASS` "
        "(Note, Literature, Report, Finding, Plan, Roadmap, Todo, Milestone, Observation, or Delegation)."
    ),
    "knowledge.stray": (
        "knowledges/ holds documents (<slug>.md or <slug>.html) and figs/ only. Keep data "
        "with the run that made it (`molab runs adopt`) or import it as an asset "
        "(`molab asset import`)."
    ),
    "knowledge.duplicate": (
        "A document name has one file: keep either <slug>.md or <slug>.html and "
        "delete the other (`molab knowledge delete`)."
    ),
    "knowledge.section_drift": (
        "The index.knowledges section disagrees with the documents; run `molab index sync`."
    ),
    **CONTENT_RULE_HINTS,
}


def known_classes() -> frozenset[str]:
    """The document class names a frontmatter ``class:`` may spell."""
    from .concepts import _PRODUCTS

    return frozenset(_PRODUCTS)


def classify_document(name: str, is_dir: bool) -> str | None:
    """Whether *name* may sit in a ``knowledges/`` container; the rule it breaks.

    A document file and the ``figs/`` directory may. Pure: the content (its
    ``class:``) is judged separately.
    """
    if is_dir:
        return None if name == KNOWLEDGE_MEDIA_DIR else "knowledge.stray"
    if not is_knowledge_file(name):
        return "knowledge.stray"
    return None


def duplicate_documents(names: Iterable[str], name: str) -> list[str]:
    """The entries of *names* that share *name*'s document stem, *name* excluded.

    ``a.md`` and ``a.html`` are one document name stored twice.
    """
    if not is_knowledge_file(name):
        return []
    stem = knowledge_stem(name)
    return sorted(
        other
        for other in names
        if other != name and is_knowledge_file(other) and knowledge_stem(other) == stem
    )


def _issue(root: str, path: str, rule: str, detail: str, severity: str) -> dict[str, str]:
    prefix = root.rstrip("/") + "/"
    rel = path[len(prefix) :] if path.startswith(prefix) else path
    return {
        "path": rel or ".",
        "rule": rule,
        "detail": detail,
        "severity": severity,
        "hint": RULE_HINTS[rule],
    }


def class_problem(text: str, *, path: object = None) -> str | None:
    """Why *text* (the document at *path*) is not of a known class, or ``None``."""
    from .frontmatter import split_frontmatter
    from .naming import is_html_document

    meta, _body = split_frontmatter(text, path=path)
    head = "record" if path is not None and is_html_document(path) else "frontmatter"
    declared = meta.get("class")
    if not isinstance(declared, str) or not declared:
        return f"{head} has no class:"
    if declared not in known_classes():
        return f"{head} class {declared!r} is not one of {sorted(known_classes())}"
    return None


def _check_section(
    workspace: Workspace, host: str, fs: FileSystem, root: str
) -> dict[str, str] | None:
    from .index_section import SECTION_KEY, section_rows

    folder = workspace.folder_at(host)
    if folder is None:
        return None
    found = folder.index_section(SECTION_KEY) or []
    expected = section_rows(host, fs=fs)
    if found == expected:
        return None
    from molab.workspace.entity_record import INDEX_FILENAME

    return _issue(
        root,
        fs.join(host, INDEX_FILENAME),
        "knowledge.section_drift",
        f"index.{SECTION_KEY} lists {len(found)} row(s); the documents give {len(expected)}",
        "warning",
    )


def _host_in_scope(rel: str, scope: frozenset[str] | None) -> bool:
    """The workspace host, a scoped project's own level, or a scoped experiment and its runs."""
    if scope is None or rel in ("", "."):
        return True
    return any(
        rel == item or ("/experiments/" in item and rel.startswith(item + "/")) for item in scope
    )


def validate_knowledge(
    root: PathArg | Workspace,
    *,
    fs: FileSystem | None = None,
    errors_only: bool = False,
    scope: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Check every host's ``knowledges/`` under the workspace at *root*.

    Args:
        root: The workspace root directory, or a loaded ``Workspace``.
        fs: Filesystem to read through; the workspace's own (or the local one)
            when omitted.
        errors_only: Skip ``knowledge.section_drift``, which is always a
            warning and loads every host's record to compare its ``index:``
            section.
        scope: Workspace-relative project / experiment directories, as for
            :func:`molab.workspace.validate.validate_workspace`; ``None``
            checks every host.

    Returns:
        Issue dicts (``path`` relative to the root, ``rule``, ``detail``,
        ``severity``, ``hint``), in walk order. Empty when nothing is wrong
        or *root* is not a workspace.
    """
    from molab.workspace import Workspace

    from .concept import read_text_or_none

    if isinstance(root, Workspace):
        workspace = root
        disk = fs or root.fs
    else:
        disk = fs or LocalFS()
        try:
            workspace = Workspace.load(root, fs=disk)
        except FileNotFoundError:
            return []
    base = str(workspace.resolve())
    wanted = None if scope is None else frozenset(scope)
    issues: list[dict[str, str]] = []
    documents: list[str] = []
    for host_path in Workspace.list_hosts(base, fs=disk):
        host = str(host_path)
        prefix = base.rstrip("/") + "/"
        rel = host[len(prefix) :] if host.startswith(prefix) else ""
        if not _host_in_scope(rel, wanted):
            continue
        container = disk.join(host, KNOWLEDGE_CONTAINER)
        try:
            entries = disk.ls(container, A=True, l=True)
        except OSError:
            entries = []
        names = [entry.name for entry in entries if not entry.is_dir]
        for entry in sorted(entries, key=lambda item: item.name):
            path = disk.join(container, entry.name)
            rule = classify_document(entry.name, entry.is_dir)
            if rule is not None:
                kind = "directory" if entry.is_dir else "file"
                issues.append(
                    _issue(base, path, rule, f"{entry.name!r} is not a document {kind}", "error")
                )
                continue
            if entry.is_dir:
                continue
            twins = duplicate_documents(names, entry.name)
            if twins:
                detail = f"{entry.name!r} and {', '.join(map(repr, twins))} are one document name"
                issues.append(_issue(base, path, "knowledge.duplicate", detail, "error"))
            problem = class_problem(read_text_or_none(path, fs=disk) or "", path=path)
            if problem is not None:
                issues.append(_issue(base, path, "knowledge.class", problem, "error"))
            else:
                documents.append(path)
        if errors_only:
            continue
        drift = _check_section(workspace, host, disk, base)
        if drift is not None:
            issues.append(drift)
    for found in content_issues(documents, root=base, fs=disk, errors_only=errors_only):
        issues.append(_issue(base, found.path, found.rule, found.detail, found.severity))
    return issues
