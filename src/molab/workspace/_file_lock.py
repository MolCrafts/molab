"""Advisory inter-process file locking — re-export shim.

The implementation moved to the cross-layer primitive
:mod:`molab.atomicio` (okf-01-01) — a cross-layer primitive shared by
workspace and knowledge. ``file_lock`` /
``FileLockTimeoutError`` / ``DEFAULT_LOCK_TIMEOUT_SECONDS`` remain
importable from ``molab.workspace._file_lock`` (same objects) for
back-compat; new code may import them from ``molab.atomicio`` directly.
"""

from __future__ import annotations

from molab.atomicio import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    FileLockTimeoutError,
    file_lock,
)

__all__ = ["DEFAULT_LOCK_TIMEOUT_SECONDS", "FileLockTimeoutError", "file_lock"]
