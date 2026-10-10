"""Dataset preview through molpy's per-format readers.

A dataset previews through its same-stem ``.py`` sidecar, which names the
dataset's reader in one module-level variable, :data:`SIDECAR_READER`: a
callable that takes the dataset path and returns a :class:`FrameReader`.
molpy's per-format readers are exactly that, so the sidecar of a file molpy
can parse is one line::

    import molpy as mp

    READER = mp.io.lammps.LammpsDumpReader

A dataset in a format of its own names a class with ``n_frames`` and
``read_frame(index)`` instead; it can wrap a per-format reader, or build its
frames with ``molpy.Frame``. Either way molab never parses a dataset itself.

This module tracks molpy's public surface; the host
(:mod:`molab.server.preview`) only finds the sidecar and caps the frames.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from molab.server.exceptions import NoReaderInSidecarError, PreviewReaderError

if TYPE_CHECKING:
    from molpy import Frame

#: The sidecar variable that names the dataset's reader.
SIDECAR_READER = "READER"


@runtime_checkable
class FrameReader(Protocol):
    """What a preview reads frames through.

    molpy's per-format readers (``mp.io.xyz.XyzReader``,
    ``mp.io.lammps.LammpsDumpReader``, ``mp.io.pdb.PdbReader``, …) satisfy it
    as they are.
    """

    @property
    def n_frames(self) -> int:
        """Number of frames in the dataset."""
        ...

    def read_frame(self, index: int) -> Frame:
        """The frame at *index*."""
        ...


def open_reader(sidecar: ModuleType, dataset_path: Path) -> FrameReader:
    """Open *dataset_path* with the reader the *sidecar* names.

    Raises:
        NoReaderInSidecarError: The sidecar defines no :data:`SIDECAR_READER`.
        PreviewReaderError: The reader cannot be opened on the dataset, or
            what it returns is not a :class:`FrameReader`.
    """
    sidecar_path = str(getattr(sidecar, "__file__", dataset_path))
    reader_factory = getattr(sidecar, SIDECAR_READER, None)
    if reader_factory is None:
        raise NoReaderInSidecarError(sidecar_path)
    if not callable(reader_factory):
        raise PreviewReaderError(
            str(dataset_path), f"{SIDECAR_READER} in {sidecar_path} is not callable"
        )
    try:
        reader = reader_factory(dataset_path)
    except Exception as exc:
        raise PreviewReaderError(str(dataset_path), f"opening the reader failed: {exc}") from exc
    if not isinstance(reader, FrameReader):
        raise PreviewReaderError(
            str(dataset_path),
            f"{SIDECAR_READER} returned a {type(reader).__name__}, "
            "which has no n_frames / read_frame(index)",
        )
    return reader


def frames_to_extxyz(frames: Sequence[Frame]) -> bytes:
    """Encode *frames* as one extended-XYZ trajectory (``molpy.io.write_xyz_str``)."""
    from molpy.io import write_xyz_str

    try:
        return "".join(write_xyz_str(frame) for frame in frames).encode()
    except Exception as exc:
        raise PreviewReaderError("<frames>", f"write_xyz_str failed: {exc}") from exc
