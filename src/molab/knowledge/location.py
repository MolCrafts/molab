"""Where a Knowledge document lands — the one derivation, and the host protocol.

A document has exactly one place under its host: ``<host>/knowledges/<slug>``,
carrying the ``.md`` suffix when the Knowledge class is a ``FILE_DOCUMENT``
(the six built-ins) and keeping the bare directory otherwise. This module owns
that derivation; callers no longer need to know which form a class lands in.

**The host protocol is fixed, and permanent.** A ``str`` / :class:`os.PathLike`
host is used as given — never resolved, so ``..`` survives. An object host must
carry ``_disk()`` (the ``Folder`` family), and is resolved through
:meth:`~molab.workspace.folder.Folder.resolve` rather than its lazy-mkdir
``path``. Anything else — including an object with ``resolve()`` but no
``_disk()``, such as a :class:`~molab.knowledge.concept.Concept` — raises
``TypeError``: a host is never guessed, and never silently handed the local
filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from molab.fs import FileSystem, LocalFileSystem, PathArg
from molab.ids import slugify

from .naming import KNOWLEDGE_CONTAINER, as_knowledge_file

if TYPE_CHECKING:
    from .concept import Concept

__all__ = ["folder"]


class DiskHost(Protocol):
    """A ``Folder``-family host: an absolute directory plus the disk holding it."""

    def resolve(self) -> PathArg:
        """This host's absolute directory, without the lazy mkdir ``path`` does."""
        ...

    def _disk(self) -> FileSystem:
        """The filesystem this host lives on — also how an object host is recognised."""
        ...


def folder(host: PathArg | DiskHost, name: str, of: type[Concept]) -> Path:
    """The landed path of the *of* document named *name* under *host*.

    Args:
        host: Where the document lives — a ``str`` / :class:`os.PathLike`
            directory (used as given), or an object carrying ``_disk()``
            (a workspace ``Folder``, walked to its absolute directory).
        name: Human document name; slugified, falling back to the raw name
            when it slugifies to nothing (a CJK-only name).
        of: The Knowledge class. A ``FILE_DOCUMENT`` class (the six built-ins)
            lands at ``<host>/knowledges/<slug>.md``; a directory-form class
            at ``<host>/knowledges/<slug>/``.

    Returns:
        The document's own path: the markdown file for a ``FILE_DOCUMENT``
        class, the directory for a directory-form one.

    Raises:
        TypeError: If *host* is neither a ``str`` / :class:`os.PathLike` nor an
            object carrying ``_disk()``.
    """
    container = _host_dir(host) / KNOWLEDGE_CONTAINER / (slugify(name) or name)
    if of.FILE_DOCUMENT:
        return Path(as_knowledge_file(str(container)))
    return container


def _host_dir(host: PathArg | DiskHost) -> Path:
    """The absolute directory *host* denotes, without touching disk.

    Args:
        host: A path, or an object carrying ``_disk()``.

    Returns:
        A path host verbatim; an object host's :meth:`~DiskHost.resolve`.

    Raises:
        TypeError: If *host* is neither.
    """
    if isinstance(host, (str, os.PathLike)):
        return Path(str(host))
    if hasattr(host, "_disk"):
        return Path(str(host.resolve()))
    raise _bad_host(host)


def _host_disk(host: PathArg | DiskHost) -> FileSystem:
    """The filesystem *host* lives on — the ``fs`` a ``(host, name)`` construction adopts.

    Args:
        host: A path, or an object carrying ``_disk()``.

    Returns:
        The host's own disk for an object host, :class:`~molab.fs.LocalFileSystem`
        for a path host.

    Raises:
        TypeError: If *host* is neither — never a fallback to the local disk.
    """
    if isinstance(host, (str, os.PathLike)):
        return LocalFileSystem()
    disk = getattr(host, "_disk", None)
    if disk is None:
        raise _bad_host(host)
    return disk()


def _bad_host(host: object) -> TypeError:
    """The one rejection message for an unrecognised host."""
    return TypeError(
        f"knowledge host must be a str/os.PathLike path or an object with _disk(), "
        f"got {type(host).__name__}"
    )
