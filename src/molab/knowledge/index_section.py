"""The ``index.knowledges`` section of each host's ``index.md``.

A host (the workspace root, a project, an experiment, a run) lists the
documents under its ``knowledges/`` in its own ``index.md`` frontmatter, so an
agent walking the tree from the root ``index.md`` sees them without listing a
directory. Workspace owns that file; knowledge only asks, through the opaque
``Folder.set_index_section`` (D89), and workspace never learns what the
section means.

Each row is ``{path, class, title}``: ``path`` is relative to the host's
``index.md`` (``knowledges/<slug>.md``), ``class`` is the frontmatter class,
and ``title`` is the frontmatter ``title``, else the first H1, else the
document name. Rows are sorted by path.

The section is rebuilt from the files, never edited: after ``write_knowledge``,
``rename``, ``move_to`` and ``delete`` (:func:`refresh_section`), and whole by
``molab index sync`` (:func:`rebuild_sections`). Like the derived ``index:``
keys it is navigation sugar: a refresh that fails is logged, never raised,
and a host that is not a workspace Folder (a plain directory) is skipped.

``molab.workspace`` is imported only inside function bodies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from molab._typing import JSONValue
from molab.fs import FileSystem, LocalFS, PathArg

from .naming import KNOWLEDGE_CONTAINER, is_knowledge_file

if TYPE_CHECKING:
    from molab.workspace import Folder, Workspace

_LOG = logging.getLogger(__name__)

#: The section key under ``index:``; the same word as the container.
SECTION_KEY = KNOWLEDGE_CONTAINER

__all__ = [
    "SECTION_KEY",
    "host_folder",
    "rebuild_sections",
    "refresh_section",
    "section_rows",
]


def _title(meta: dict[str, object], body: str, fallback: str) -> str:
    from .search import extract_title

    for value in (meta.get("title"), extract_title(body), meta.get("name")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def section_rows(host_dir: PathArg, *, fs: FileSystem) -> list[dict[str, JSONValue]]:
    """The ``index.knowledges`` rows for the host at *host_dir*, built from the files.

    Only document files (``.md`` / ``.html``) directly under ``knowledges/`` are documents; anything
    else there is reported by :mod:`molab.knowledge.validate`, not listed.
    """
    from .concept import read_text_or_none
    from .frontmatter import split_frontmatter

    container = fs.join(host_dir, KNOWLEDGE_CONTAINER)
    try:
        entries = fs.ls(container, A=True, l=True)
    except OSError:
        return []
    rows: list[dict[str, JSONValue]] = []
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.is_dir or not is_knowledge_file(entry.name):
            continue
        text = read_text_or_none(fs.join(container, entry.name), fs=fs) or ""
        meta, body = split_frontmatter(text, path=entry.name)
        declared = meta.get("class")
        stem = entry.name.rsplit(".", 1)[0]
        rows.append(
            {
                "path": f"{KNOWLEDGE_CONTAINER}/{entry.name}",
                "class": declared if isinstance(declared, str) else "",
                "title": _title(meta, body, stem),
            }
        )
    return rows


def host_folder(
    host_dir: PathArg, *, fs: FileSystem, workspace: Workspace | None = None
) -> Folder | None:
    """The workspace Folder whose directory is *host_dir*, or ``None``.

    Args:
        host_dir: A host directory.
        fs: The disk.
        workspace: The workspace to resolve in; found from *host_dir* when
            omitted.

    Returns:
        The root, project, experiment or run Folder, or ``None`` for a
        directory that is not one (outside any workspace, or no record).
    """
    from molab.workspace import Workspace

    if workspace is None:
        root = Workspace.enclosing_root(host_dir, fs=fs)
        if root is None:
            return None
        workspace = Workspace(root, fs=fs)
    return workspace.folder_at(host_dir)


def _write_section(folder: Folder, rows: list[dict[str, JSONValue]]) -> bool:
    """Write *rows* unless they are already there; an empty, absent section stays absent."""
    current = folder.index_section(SECTION_KEY)
    if current == rows or (current is None and not rows):
        return False
    folder.set_index_section(SECTION_KEY, rows)
    return True


def refresh_section(
    document_path: PathArg,
    *,
    fs: FileSystem | None = None,
    root: PathArg | None = None,
    known_root: bool = False,
) -> None:
    """Rebuild the section of the host holding *document_path*. Never raises.

    The document need not exist (after ``delete`` or the old side of a
    ``move_to``). A document outside a ``knowledges/`` container, or under a
    host that is not a workspace Folder, changes nothing.

    Args:
        document_path: The document whose host is rebuilt.
        fs: The disk; the local one when omitted.
        root: The enclosing workspace root, when the caller already found it.
        known_root: *root* is the caller's answer, ``None`` included (no
            workspace): the enclosing root is not looked up again.
    """
    from .location import host_of

    disk = fs if fs is not None else LocalFS()
    try:
        path = str(document_path)
        if disk.basename(disk.dirname(path)) != KNOWLEDGE_CONTAINER:
            return
        host = str(host_of(path))
        if known_root:
            if root is None:
                return
            from molab.workspace import Workspace

            folder = Workspace(root, fs=disk).folder_at(host)
        else:
            folder = host_folder(host, fs=disk)
        if folder is None:
            return
        _write_section(folder, section_rows(host, fs=disk))
    except Exception as exc:
        _LOG.warning("index.%s refresh failed for %s: %s", SECTION_KEY, document_path, exc)


def rebuild_sections(workspace: Workspace) -> int:
    """Rebuild the section of every host in *workspace*. Returns sections written.

    A host with no documents and no section is left without one.
    """
    from molab.workspace import Workspace

    fs = workspace.fs
    written = 0
    for host in Workspace.list_hosts(workspace.resolve(), fs=fs):
        folder = workspace.folder_at(host)
        if folder is None:
            continue
        if _write_section(folder, section_rows(str(host), fs=fs)):
            written += 1
    return written
