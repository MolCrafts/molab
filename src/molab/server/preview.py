"""Sidecar-backed dataset preview — host half.

The host finds the same-stem ``.py`` sidecar, imports it under a private
name, and caps the frames it reads. Science lives in plugins:

* :mod:`molab.plugins.molpy.preview` — the sidecar's reader
  (:class:`~molab.plugins.molpy.preview.FrameReader`, satisfied by molpy's
  per-format readers) and extended-XYZ encoding
* :mod:`molab.plugins.molvis.snapshot` — PNG via molvis

When molpy/molvis change, update those plugins — not this module.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from .exceptions import (
    MolabError,
    NoReaderInSidecarError,
    PreviewReaderError,
    PreviewSidecarNotFoundError,
)

if TYPE_CHECKING:
    from molpy import Frame

    from molab.plugins.molpy.preview import FrameReader

_SIDECAR_MODULE_NAME = "_molab_preview_reader"
DEFAULT_PREVIEW_LIMIT = 200

__all__ = [
    "DEFAULT_PREVIEW_LIMIT",
    "NoReaderInSidecarError",
    "PreviewReaderError",
    "PreviewSidecarNotFoundError",
    "SidecarInfo",
    "frames_to_extxyz",
    "load_preview",
    "preview_frames",
    "resolve_sidecar",
    "snapshot_reader",
]


@dataclass(frozen=True)
class SidecarInfo:
    """Result of existence-only sidecar resolution."""

    dataset_path: Path
    sidecar_path: Path


def _sidecar_path_for(dataset_path: Path) -> Path:
    stem = dataset_path.name.split(".", 1)[0]
    return dataset_path.parent / f"{stem}.py"


def resolve_sidecar(dataset_path: str | os.PathLike[str]) -> SidecarInfo | None:
    """Probe for a same-stem ``.py`` sidecar without importing it."""
    path = Path(dataset_path)
    sidecar = _sidecar_path_for(path)
    if sidecar == path or not sidecar.is_file():
        return None
    return SidecarInfo(dataset_path=path, sidecar_path=sidecar)


def _import_sidecar_module(sidecar_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(_SIDECAR_MODULE_NAME, sidecar_path)
    if spec is None or spec.loader is None:
        raise PreviewReaderError(str(sidecar_path), "cannot create import spec")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PreviewReaderError(str(sidecar_path), f"import failed: {exc}") from exc
    return module


def load_preview(dataset_path: str | os.PathLike[str]) -> FrameReader:
    """Import the sidecar and open the reader it names (molpy plugin)."""
    info = resolve_sidecar(dataset_path)
    if info is None:
        raise PreviewSidecarNotFoundError(str(dataset_path))
    module = _import_sidecar_module(info.sidecar_path)
    from molab.plugins.molpy.preview import open_reader

    return open_reader(module, info.dataset_path)


def preview_frames(
    dataset_path: str | os.PathLike[str], *, limit: int = DEFAULT_PREVIEW_LIMIT
) -> list[Frame]:
    """Return the first *limit* frames at most. Cap is host-owned."""
    reader = load_preview(dataset_path)
    try:
        return [reader.read_frame(index) for index in range(min(limit, reader.n_frames))]
    except MolabError:
        raise
    except Exception as exc:
        raise PreviewReaderError(str(dataset_path), f"reading frames failed: {exc}") from exc


def frames_to_extxyz(frames: list[Frame]) -> bytes:
    """Delegate XYZ encoding to the molpy plugin."""
    from molab.plugins.molpy.preview import frames_to_extxyz as encode

    return encode(frames)


def snapshot_reader(
    dataset_path: str | os.PathLike[str], *, limit: int = DEFAULT_PREVIEW_LIMIT
) -> bytes:
    """Delegate PNG rendering to the molvis plugin."""
    from molab.plugins.molvis.snapshot import render_png

    return render_png(preview_frames(dataset_path, limit=limit), dataset_path=str(dataset_path))
