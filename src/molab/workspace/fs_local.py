"""Re-export shim — ``LocalFS`` moved to :mod:`molab.fs.local`.

Re-exports the *same class object*, so ``isinstance(fs, LocalFS)``
checks keep agreeing no matter which import path a caller used.
"""

from molab.fs.local import LocalFS

__all__ = ["LocalFS"]
