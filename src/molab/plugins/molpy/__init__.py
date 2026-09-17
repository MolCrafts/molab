"""molpy plugin — science I/O molab uses through molpy's public API.

When molpy/molrs change, this package is what updates. The host
(``molab.server``) only discovers sidecar files and applies the frame cap.
"""

from __future__ import annotations

from molab.plugins.molpy.preview import (
    frames_to_extxyz,
    open_reader,
    readers_in,
)

__all__ = [
    "frames_to_extxyz",
    "open_reader",
    "readers_in",
]
