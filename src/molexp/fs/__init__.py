"""``molexp.fs`` — the filesystem seam, a cross-layer primitive.

Where files and directories actually live. A :class:`FileSystem` is a
``runtime_checkable`` Protocol with two first-party implementations:
:class:`LocalFileSystem` (stdlib) and, in the workspace layer,
``RemoteFileSystem`` / ``CachedRemoteFileSystem`` (molq-backed SSH mirrors).

It sits at the package root — beside ``path`` / ``ids`` / ``atomicio`` — rather
than inside ``workspace`` because **two** bottom layers speak it:
``molexp.workspace`` (the Folder family) and ``molexp.knowledge`` (the OKF
Concept bundle, which must work on a plain directory with no workspace in
sight). One Protocol and one ``LocalFileSystem`` class shared by both is
load-bearing, not tidiness: ``Folder.move_to`` gates on
``isinstance(self._fs, LocalFileSystem)``, so a second, parallel
``LocalFileSystem`` would make that check silently False for a perfectly local
tree.

Only the Protocol and the stdlib implementation are eager here. The molq-backed
remote filesystems stay in ``molexp.workspace`` (``fs_remote`` / ``fs_cached``),
so ``import molexp.fs`` never pulls ``molq`` — a knowledge bundle opened over a
plain directory imports stdlib and nothing else.
"""

from .base import FileSystem, PathArg, StatResult
from .local import LocalFileSystem

__all__ = ["FileSystem", "LocalFileSystem", "PathArg", "StatResult"]
