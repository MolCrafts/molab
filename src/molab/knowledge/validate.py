"""Validate the knowledge documents of a workspace. Read-only.

The workspace validator holds the tree to the layout law and does not know
``knowledges/`` (a layer above it declares that container). This module
checks what lives inside it, at every host (the root, each project,
experiment and run):

* ``knowledge.class`` (error) — a document whose frontmatter has no ``class:``
  or names a class that is not one of the six.
* ``knowledge.stray`` (error) — an entry of ``knowledges/`` that is not a
  markdown document (a directory, a data file).
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

from typing import TYPE_CHECKING

from molab.fs import FileSystem, LocalFS, PathArg

from .naming import KNOWLEDGE_CONTAINER, is_knowledge_file

if TYPE_CHECKING:
    from molab.workspace import Workspace

__all__ = [
    "RULE_HINTS",
    "classify_document",
    "known_classes",
    "validate_knowledge",
]

#: Stable rule id -> remediation hint naming the molab command to use.
RULE_HINTS: dict[str, str] = {
    "knowledge.class": (
        "A knowledge document names its class in frontmatter. Write it with "
        "`molab knowledge write NAME TEXT --on HOST --class CLASS` "
        "(Note, Literature, Report, Finding, Plan or Observation)."
    ),
    "knowledge.stray": (
        "knowledges/ holds markdown documents only. Keep data with the run that "
        "made it (`molab runs adopt`) or import it as an asset (`molab asset import`)."
    ),
    "knowledge.section_drift": (
        "The index.knowledges section disagrees with the documents; run `molab index sync`."
    ),
}


def known_classes() -> frozenset[str]:
    """The six document class names a frontmatter ``class:`` may spell."""
    from .concepts import _PRODUCTS

    return frozenset(_PRODUCTS)


def classify_document(name: str, is_dir: bool) -> str | None:
    """Whether *name* may sit in a ``knowledges/`` container; the rule it breaks.

    Pure: the content (its ``class:``) is judged separately.
    """
    if is_dir or not is_knowledge_file(name):
        return "knowledge.stray"
    return None


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


def class_problem(text: str) -> str | None:
    """Why *text* is not a knowledge document of a known class, or ``None``."""
    from .frontmatter import split_frontmatter

    meta, _body = split_frontmatter(text)
    declared = meta.get("class")
    if not isinstance(declared, str) or not declared:
        return "frontmatter has no class:"
    if declared not in known_classes():
        return f"frontmatter class {declared!r} is not one of {sorted(known_classes())}"
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


def validate_knowledge(
    root: PathArg | Workspace, *, fs: FileSystem | None = None
) -> list[dict[str, str]]:
    """Check every host's ``knowledges/`` under the workspace at *root*.

    Args:
        root: The workspace root directory, or a loaded ``Workspace``.
        fs: Filesystem to read through; the workspace's own (or the local one)
            when omitted.

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
    issues: list[dict[str, str]] = []
    for host_path in Workspace.list_hosts(base, fs=disk):
        host = str(host_path)
        container = disk.join(host, KNOWLEDGE_CONTAINER)
        try:
            entries = disk.ls(container, A=True, l=True)
        except OSError:
            entries = []
        for entry in sorted(entries, key=lambda item: item.name):
            path = disk.join(container, entry.name)
            rule = classify_document(entry.name, entry.is_dir)
            if rule is not None:
                kind = "directory" if entry.is_dir else "file"
                issues.append(
                    _issue(base, path, rule, f"{entry.name!r} is not a markdown {kind}", "error")
                )
                continue
            problem = class_problem(read_text_or_none(path, fs=disk) or "")
            if problem is not None:
                issues.append(_issue(base, path, "knowledge.class", problem, "error"))
        drift = _check_section(workspace, host, disk, base)
        if drift is not None:
            issues.append(drift)
    return issues
