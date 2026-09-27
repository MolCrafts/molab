"""Detect which *foreign log* formats a run directory holds.

This is about **source logs**, not scientific record packages. Whether a
directory is a MolRec record is defined by the external molrec spec (Zarr V3
root + group attributes); molab does not re-host that contract.

Detection is **by content, never by extension**. ``leap.log`` and
``log.lammps`` share a suffix and nothing else; a ``.csv`` of atom
coordinates is not a metrics table. Every probe reads a bounded prefix of
the candidate file and looks for a marker the format actually guarantees.

A file nobody can classify yields :attr:`LogFormat.UNKNOWN`, which is a
correct answer — the caller leaves it as a plain artifact rather than
approximating a conversion.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_TFEVENT_PREFIX = "events.out.tfevents."


class LogFormat(StrEnum):
    """Format ids molab itself needs to name.

    Formats are owned by the packages that can parse them and arrive through
    the reader registry, so this is not a closed vocabulary — a
    :class:`FormatHit` carries whatever id its reader declared. Only the
    "recognised as nothing" case belongs to molab.
    """

    UNKNOWN = "unknown"
    """Recognised as nothing. Never read."""


@dataclass(frozen=True, slots=True)
class FormatHit:
    """One detected format inside a run directory."""

    format: str
    """The reader's format id. Well-known ones are named by :class:`LogFormat`,
    but a reader registered by another package brings its own."""

    path: Path
    """The file (or directory, for TensorBoard) that carries the format."""

    detail: str = ""
    """Short human-readable reason, for the operator-facing report."""


def has_metrics_buffer(run_dir: Path) -> bool:
    """True when *run_dir* already carries a JSONL metrics WAL."""
    from molab.plugins.metrics import has_metrics

    return has_metrics(run_dir)


def _iter_files(run_dir: Path, *, max_depth: int) -> Iterator[Path]:
    roots = [(run_dir, 0)]
    while roots:
        current, depth = roots.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.startswith("."):
                continue
            if child.is_dir():
                if depth < max_depth:
                    roots.append((child, depth + 1))
            else:
                yield child


def detect_log_formats(run_dir: Path | str, *, max_depth: int = 3) -> list[FormatHit]:
    """Classify every ingestible log under *run_dir*.

    Args:
        run_dir: Directory to classify.
        max_depth: How deep to descend when looking for artifacts.

    Returns:
        One :class:`FormatHit` per detected artifact; an empty list when the
        directory holds nothing an ingester recognises.
    """
    from .readers import sniff as sniff_readers

    root = Path(run_dir)
    hits: list[FormatHit] = []
    seen_dirs: set[Path] = set()

    for path in _iter_files(root, max_depth=max_depth):
        # A directory-shaped format (TensorBoard) is claimed once, by its
        # parent, no matter how many files it holds.
        if path.name.startswith(_TFEVENT_PREFIX):
            parent = path.parent
            if parent not in seen_dirs:
                seen_dirs.add(parent)
                reader = sniff_readers(parent)
                if reader is not None:
                    hits.append(FormatHit(reader.format, parent, "tfevents files"))
            continue
        reader = sniff_readers(path)
        if reader is not None:
            hits.append(FormatHit(reader.format, path, f"claimed by the {reader.format} reader"))

    return hits
