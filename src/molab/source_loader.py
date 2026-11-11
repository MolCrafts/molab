"""Import user scripts from source, never from a cached ``.pyc``.

Shared by ``molab run`` (:mod:`molab.entry`) and the workflow loader. Kept
free of molab imports so the workflow layer still loads lazily.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
from types import CodeType


class _SourceOnlyLoader(importlib.machinery.SourceFileLoader):
    """A file loader that always compiles the source and never touches ``__pycache__``.

    The default loader trusts a cached ``.pyc`` whose recorded mtime (whole
    seconds) and size match the file. A script edited within the same second
    without changing its length (``= 1`` → ``= 2``) therefore runs stale
    bytecode. User scripts are edited and rerun that quickly, so they are
    compiled from source every time.
    """

    def get_code(self, fullname: str) -> CodeType:  # noqa: ARG002 - importlib's signature; the path is the identity
        source = self.get_data(self.path)
        return compile(source, self.path, "exec", dont_inherit=True)


def spec_from_source(name: str, path: Path) -> importlib.machinery.ModuleSpec | None:
    """A module spec for *path* under *name* that compiles from source (no ``.pyc``)."""
    return importlib.util.spec_from_file_location(
        name, path, loader=_SourceOnlyLoader(name, str(path))
    )
