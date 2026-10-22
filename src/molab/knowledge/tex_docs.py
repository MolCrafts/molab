"""TeX files the knowledge list shows, without making them knowledge documents.

A knowledge document stays ``<host>/knowledges/<slug>.md``. A manuscript is a
different file: ``<host>/manuscript/*.tex`` (one directory level, so
``figures/tab_*.tex`` stays a fragment) and, when someone places one there,
``<host>/knowledges/*.tex``. The directory tree is the index. Knowledge reads
these paths and does not write them.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import PurePosixPath

from molab.fs.base import FileSystem, PathArg

TEX_CLASS = "Tex"
"""Wire class for a TeX row. It is not one of the six Knowledge classes."""

TEX_SUFFIXES: tuple[str, ...] = (".tex", ".ltx")
MANUSCRIPT_CONTAINER = "manuscript"


def is_tex_file(path: str) -> bool:
    """Whether *path* names a ``.tex`` or ``.ltx`` file."""
    return PurePosixPath(path).suffix.lower() in TEX_SUFFIXES


def tex_host_path(rel_path: str) -> str:
    """Workspace-relative host of a listed TeX file.

    The file sits in ``manuscript/`` or ``knowledges/`` directly under its
    host, so the host is the path with those two trailing parts removed.
    """
    parts = PurePosixPath(rel_path).parts
    if len(parts) < 2:
        return ""
    return PurePosixPath(*parts[:-2]).as_posix() if len(parts) > 2 else ""


def iter_tex_documents(root: PathArg, fs: FileSystem) -> Iterator[str]:
    """Yield absolute paths of TeX files the knowledge list shows.

    Each workspace host (the root, then every project, experiment, and run)
    contributes the files in ``manuscript/`` and ``knowledges/``, one level
    deep. A missing directory is skipped. Names are sorted.

    Args:
        root: Workspace root. Its spelling is kept.
        fs: Filesystem to list.

    Yields:
        Absolute paths joined from *root*.
    """
    from molab.workspace import Workspace

    from .naming import KNOWLEDGE_CONTAINER

    containers = (MANUSCRIPT_CONTAINER, KNOWLEDGE_CONTAINER)
    for host in Workspace.list_hosts(root, fs=fs):
        for container in containers:
            directory = fs.join(str(host), container)
            try:
                entries = fs.scandir(directory, with_stat=False)
            except (OSError, ValueError):
                continue
            files = sorted(
                (entry for entry in entries if entry.is_file and is_tex_file(entry.name)),
                key=lambda entry: entry.name,
            )
            for entry in files:
                yield fs.join(directory, entry.name)
