"""Where a Knowledge document lands — the one derivation, and the host protocol.

A document has exactly one place under its host:
``<host>/knowledges/<slug>.md``. A bare :class:`Concept` is not a document
class and :func:`folder` raises ``TypeError``. This module owns that
derivation.

**The host protocol is fixed.** A ``str`` / :class:`os.PathLike` host is used
as given — never resolved, so ``..`` survives. A workspace
:class:`~molab.workspace.folder.Folder` contributes its
:attr:`~molab.workspace.folder.Folder.fs` and
:meth:`~molab.workspace.folder.Folder.resolve`. A bare ``Knowledge`` tree
handle uses the one container rule (:func:`bare_container`): a workspace root
lands in ``knowledges/``, a plain wiki is its own container, and a directory
inside a workspace that is not the root is rejected. A document instance does
not nest. Anything else raises ``TypeError``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from molab.fs import FileSystem, LocalFileSystem, PathArg
from molab.ids import slugify

from .naming import KNOWLEDGE_CONTAINER, as_knowledge_file

if TYPE_CHECKING:
    from molab.workspace import Folder

    from .concept import Concept

DOCUMENT_SLUG_MAX = 200
"""Slug budget that keeps an identifying suffix such as a UUIDv7."""

__all__ = [
    "DOCUMENT_SLUG_MAX",
    "bare_container",
    "document_slug",
    "enclosing_workspace_root",
    "folder",
    "host_of",
    "is_workspace_root",
]


def document_slug(name: str) -> str:
    """Slugify *name*, keeping up to :data:`DOCUMENT_SLUG_MAX` characters.

    A name that slugifies to nothing (a CJK-only name) is kept as given.

    Args:
        name: Human document name.

    Returns:
        The filename stem, without a suffix.
    """
    return slugify(name, max_len=DOCUMENT_SLUG_MAX) or name


def enclosing_workspace_root(path: PathArg, *, fs: FileSystem) -> Path | None:
    """The workspace root enclosing *path*, via :meth:`Workspace.enclosing_root`.

    The only call site in knowledge for that accessor. A miss is ``None``.

    Args:
        path: A file or directory, in the caller's spelling.
        fs: The disk to probe.

    Returns:
        The enclosing root, or ``None``.
    """
    from molab.workspace import Workspace

    return Workspace.enclosing_root(path, fs=fs)  # ty: ignore[invalid-return-type]


def is_workspace_root(path: PathArg, *, fs: FileSystem) -> bool:
    """Whether *path* itself is a workspace root.

    Args:
        path: A directory.
        fs: The disk to probe.

    Returns:
        ``True`` when the enclosing root is *path*.
    """
    found = enclosing_workspace_root(path, fs=fs)
    if found is None:
        return False
    from .concept import Concept

    return Concept._norm(str(found)) == Concept._norm(str(path))


def bare_container(root: PathArg, *, fs: FileSystem) -> Path:
    """The container a bare ``Knowledge`` handle writes into.

    A workspace root lands in ``<root>/knowledges``. A directory outside any
    workspace is its own container. A directory inside a workspace that is not
    the root is rejected.

    Args:
        root: The bare handle's path.
        fs: The disk the handle reads.

    Returns:
        The directory new documents land in.

    Raises:
        TypeError: If *root* lies inside a workspace and is not that root.
    """
    if is_workspace_root(root, fs=fs):
        return Path(str(root)) / KNOWLEDGE_CONTAINER
    found = enclosing_workspace_root(root, fs=fs)
    if found is None:
        return Path(str(root))
    raise TypeError(f"{root} lies inside workspace {found}; pass the workspace Folder as host")


def host_of(doc_path: PathArg) -> Path:
    """The host directory of a document path — the inverse of :func:`folder`.

    A file under ``knowledges/`` belongs to the grandparent. Any other file
    belongs to its parent (the container root).

    Args:
        doc_path: A document path.

    Returns:
        The host directory.
    """
    path = Path(str(doc_path))
    if path.parent.name == KNOWLEDGE_CONTAINER:
        return path.parent.parent
    return path.parent


def folder(host: PathArg | Folder | Concept, name: str, of: type[Concept]) -> Path:
    """The landed path of the *of* document named *name* under *host*.

    Args:
        host: A ``str`` / :class:`os.PathLike` directory (used as given), a
            workspace ``Folder``, or a bare ``Knowledge`` tree handle.
        name: Human document name; slugified, falling back to the raw name
            when it slugifies to nothing (a CJK-only name).
        of: The Knowledge class. It lands at ``<container>/<slug>.md``.

    Returns:
        The document's own path.

    Raises:
        TypeError: If *host* is a document instance, an unrecognised object,
            or a bare handle on a directory inside a workspace that is not
            the workspace root.
    """
    if not of.FILE_DOCUMENT:
        raise TypeError(f"{of.__name__} is not a knowledge document class")
    landed = _container_of(host) / document_slug(name)
    return Path(as_knowledge_file(str(landed)))


def _container_of(host: PathArg | Folder | Concept) -> Path:
    """The directory *host* puts new documents in."""
    if isinstance(host, (str, os.PathLike)):
        return Path(str(host)) / KNOWLEDGE_CONTAINER
    from molab.workspace import Folder

    if isinstance(host, Folder):
        return Path(str(host.resolve())) / KNOWLEDGE_CONTAINER
    from .concept import Concept

    if type(host) is Concept:
        return bare_container(host.path, fs=host.fs)
    raise _bad_host(host)


def _host_dir(host: PathArg | Folder) -> Path:
    """The directory *host* denotes, without touching disk.

    Args:
        host: A path, or a workspace Folder.

    Returns:
        A path host verbatim; a Folder's resolved directory.

    Raises:
        TypeError: If *host* is neither.
    """
    if isinstance(host, (str, os.PathLike)):
        return Path(str(host))
    from molab.workspace import Folder

    if isinstance(host, Folder):
        return Path(str(host.resolve()))
    raise _bad_host(host)


def _host_fs(host: PathArg | Folder | Concept) -> FileSystem:
    """The filesystem *host* lives on.

    Args:
        host: A path, a workspace Folder, or a bare Knowledge handle.

    Returns:
        The host's own disk, or :class:`~molab.fs.LocalFileSystem` for a path.

    Raises:
        TypeError: If *host* is not a recognised host.
    """
    if isinstance(host, (str, os.PathLike)):
        return LocalFileSystem()
    from molab.workspace import Folder

    if isinstance(host, Folder):
        return host.fs
    from .concept import Concept

    if type(host) is Concept:
        return host.fs
    raise _bad_host(host)


def _lookup_path(host: PathArg | Folder | Concept) -> PathArg:
    """The path passed to the workspace-root accessor for *host*."""
    if isinstance(host, (str, os.PathLike)):
        return host  # ty: ignore[invalid-return-type]
    from molab.workspace import Folder

    if isinstance(host, Folder):
        return host.resolve()
    from .concept import Concept

    if type(host) is Concept:
        return host.path
    raise _bad_host(host)


def _bad_host(host: object) -> TypeError:
    """The one rejection message for an unrecognised host."""
    return TypeError(
        "knowledge host must be a str/os.PathLike path, a workspace Folder or a "
        "bare Knowledge tree handle (documents do not nest), "
        f"got {type(host).__name__}"
    )
