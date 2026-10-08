"""Synthetic preview sidecar used by ``test_preview.py``.

Loaded via ``importlib`` under a private module name. Exercises:

* **Module-import sentinel** — discovery must not run this; explicit load must.
* **``__main__`` sentinel** — must not run under the private module name.

``READER`` names a reader of the sidecar's own: a dataset format molpy has no
reader for, building ``molpy.Frame``s itself.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from molpy import Block, Frame

_IMPORT_SENTINEL = os.environ.get("MOLEXP_TEST_IMPORT_SENTINEL")
if _IMPORT_SENTINEL:
    Path(_IMPORT_SENTINEL).write_text("imported", encoding="utf-8")


class TwoAtomReader:
    """A fixed number of two-atom frames, the second atom at x = frame index."""

    def __init__(self, path: Path, *, n_frames: int = 5) -> None:
        self.path = path
        self._n_frames = n_frames

    @property
    def n_frames(self) -> int:
        return self._n_frames

    def read_frame(self, index: int) -> Frame:
        frame = Frame()
        frame["atoms"] = Block(
            {
                "element": np.array(["C", "O"]),
                "x": np.array([0.0, float(index)]),
                "y": np.array([0.0, 0.0]),
                "z": np.array([0.0, 0.0]),
            }
        )
        return frame


READER = TwoAtomReader


if __name__ == "__main__":
    _MAIN_SENTINEL = os.environ.get("MOLEXP_TEST_MAIN_SENTINEL")
    if _MAIN_SENTINEL:
        Path(_MAIN_SENTINEL).write_text("main", encoding="utf-8")
