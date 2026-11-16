"""Headless molvis PNG of a frame sequence."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any


def render_png(frames: Sequence[Any]) -> bytes:
    """Render *frames* via ``molvis.Molvis``. Frames are molpy Frames.

    Raises:
        ImportError: molvis is not installed.
    """
    os.environ.setdefault("MOLVIS_HEADLESS", "1")
    from molvis import Molvis

    viewer = Molvis()
    viewer.set_trajectory(frames)
    return viewer.snapshot()
