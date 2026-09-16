"""Re-export shim — ``LocalFileSystem`` moved to :mod:`molexp.fs.local`.

Re-exports the *same class object*, so ``isinstance(fs, LocalFileSystem)``
checks keep agreeing no matter which import path a caller used.
"""

from molexp.fs.local import LocalFileSystem

__all__ = ["LocalFileSystem"]
