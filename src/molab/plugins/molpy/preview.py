"""Dataset preview through molpy's per-format readers.

A dataset previews through its same-stem ``.py`` sidecar, which names the
dataset's reader in one module-level variable, :data:`SIDECAR_READER`: a
callable that takes the dataset path and returns a :class:`FrameReader`.
molpy's per-format readers are exactly that, so the sidecar of a file molpy
can parse is one line::

    import molpy as mp

    READER = mp.io.lammps.LammpsDumpReader

A dataset in a format of its own names the same kind of reader: ``len`` is
the frame count and ``reader[index]`` is the frame. It can wrap a per-format
reader, or build its frames with ``molpy.Frame``. molab never parses a
dataset itself.

This module tracks molpy's public surface and raises plain Python
errors; the host (:mod:`molab.server.preview`) finds the sidecar, checks that
it names a reader, caps the frames, and turns a failure into its HTTP error.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from molpy import Frame

#: The sidecar variable that names the dataset's reader.
SIDECAR_READER = "READER"


@runtime_checkable
class FrameReader(Protocol):
    """What a preview reads frames through.

    molpy's per-format readers (``mp.io.xyz.XyzReader``,
    ``mp.io.lammps.LammpsDumpReader``, ``mp.io.pdb.PdbReader``, …) satisfy
    it as they are: ``len(reader)`` and ``reader[index]``.
    """

    def __len__(self) -> int:
        """Number of frames in the dataset."""
        ...

    def __getitem__(self, index: int) -> Frame:
        """The frame at *index*."""
        ...


def open_reader(sidecar: ModuleType, dataset_path: Path) -> FrameReader:
    """Open *dataset_path* with the reader the *sidecar* names.

    The sidecar defines :data:`SIDECAR_READER`; the host checks that before it
    calls. An error the reader raises while opening propagates.

    Raises:
        TypeError: :data:`SIDECAR_READER` is not callable, or what it returns
            is not a :class:`FrameReader`.
    """
    reader_factory = getattr(sidecar, SIDECAR_READER)
    if not callable(reader_factory):
        raise TypeError(f"{SIDECAR_READER} in {sidecar.__file__} is not callable")
    reader = reader_factory(dataset_path)
    # str, bytes, and bytearray implement len and indexing. They are not readers.
    if isinstance(reader, (str, bytes, bytearray)) or not isinstance(reader, FrameReader):
        raise TypeError(
            f"{SIDECAR_READER} returned a {type(reader).__name__}, which has no len / reader[index]"
        )
    return reader


def frames_to_extxyz(frames: Sequence[Frame]) -> bytes:
    """Encode *frames* as one extended-XYZ trajectory via molpy's public writer."""
    from molpy.io import write_xyz

    parts: list[bytes] = []
    for frame in frames:
        buf = bytearray()
        write_xyz(buf, frame)
        parts.append(bytes(buf))
    return b"".join(parts)
