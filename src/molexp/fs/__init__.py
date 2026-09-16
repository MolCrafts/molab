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

from .base import DirEntry, FileSystem, PathArg, StatResult, bulk
from .local import LocalFileSystem
from .memo import StatMemo
from .profile import (
    LOCAL_FAST_PROFILE,
    NETWORK_LOCAL_PROFILE,
    REMOTE_SSH_PROFILE,
    FsKind,
    FsProfile,
    detect_fs_profile,
)
from .window import (
    DEFAULT_TEXT_WINDOW_BYTES,
    MAX_TEXT_WINDOW_BYTES,
    TextWindow,
    read_text_window,
)

__all__ = [
    "DEFAULT_TEXT_WINDOW_BYTES",
    "LOCAL_FAST_PROFILE",
    "MAX_TEXT_WINDOW_BYTES",
    "NETWORK_LOCAL_PROFILE",
    "REMOTE_SSH_PROFILE",
    "DirEntry",
    "FileSystem",
    "FsKind",
    "FsProfile",
    "LocalFileSystem",
    "PathArg",
    "StatMemo",
    "StatResult",
    "TextWindow",
    "bulk",
    "detect_fs_profile",
    "read_text_window",
]
