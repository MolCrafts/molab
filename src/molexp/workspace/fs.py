"""Re-export shim — the filesystem seam moved to :mod:`molexp.fs`.

``FileSystem`` / ``PathArg`` / ``StatResult`` are cross-layer primitives now
(``molexp.knowledge`` speaks them too), so they live at the package root. This
shim keeps the ~50 existing ``from .fs import ...`` sites in the workspace layer
working against the *same* objects.
"""

from molexp.fs.base import DirEntry, FileSystem, PathArg, StatResult, bulk

__all__ = ["DirEntry", "FileSystem", "PathArg", "StatResult", "bulk"]
