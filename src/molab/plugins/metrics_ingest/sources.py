"""Read an attempt's metrics from whatever it actually has.

Plotting used to require a ``*.mlp.jsonl``: a solver log had to be *converted*
into molab's own format before a chart could touch it. That conversion is a
10-25x size amplification on a real thermo table, and it made "can I plot
this?" mean "has someone ingested it yet?".

So the WAL stops being the mandatory intermediate and becomes one registered
format among others. A source is anything a
:class:`~molab.plugins.metrics_ingest.readers.LogReader` claims — molab's own
WAL, a LAMMPS log via the molpy bridge, or a format some other package
registered — and reading is dispatch, not translation.

Two consumers, one seam:

* **plot** — :func:`read_sources` streams records straight to the chart.
  Nothing is written.
* **ingest** — :func:`~molab.plugins.metrics_ingest.ingest_run` persists the
  same records into the WAL, for when they should outlive their source.

Ingest is therefore an option, never a precondition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from molab._typing import JSONValue

from .detect import _iter_files
from .readers import ReadRequest, sniff

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .readers import MetricReader

DEFAULT_LIMIT = 5000
"""Records returned per read. A thermo table has far more; see *stride*."""


@dataclass(frozen=True, slots=True)
class MetricSource:
    """One file an attempt holds that some reader can turn into records."""

    path: Path
    format: str
    rel_path: str
    """Path relative to the attempt — the stable key a cursor is filed under."""

    tailable: bool = False
    """True when the file grows while the run is live (molab's own WAL)."""


@dataclass
class SourceRead:
    """Records from one source, plus where to resume."""

    source: MetricSource
    records: list[dict[str, JSONValue]] = field(default_factory=list)
    cursor: int = 0
    """Records consumed so far. Pass back as *since* to continue.

    Counted in *delivered* records, so it stays meaningful under a stride:
    resuming asks the reader to skip what the viewer already has."""

    exhausted: bool = True
    """False when the limit cut the read short."""

    error: str | None = None
    """Why this source yielded nothing, when something went wrong."""


def discover_sources(root: Path | str, *, max_depth: int = 3) -> list[MetricSource]:
    """Every plottable file under *root*, in a stable order.

    A run that never wrote a WAL still reports its solver logs, which is the
    point: discovery answers "what is here", not "what has been converted".
    """
    base = Path(root)
    found: list[MetricSource] = []
    seen_dirs: set[Path] = set()
    for path in _iter_files(base, max_depth=max_depth):
        candidates = (path, path.parent)
        for candidate in candidates:
            if candidate.is_dir():
                if candidate in seen_dirs:
                    break
                seen_dirs.add(candidate)
            reader = sniff(candidate)
            if reader is None:
                continue
            found.append(_describe(candidate, reader, base))
            break
    return sorted(found, key=lambda item: item.rel_path)


def _describe(path: Path, reader: MetricReader, base: Path) -> MetricSource:
    try:
        rel = path.relative_to(base).as_posix()
    except ValueError:
        rel = path.name
    return MetricSource(
        path=path,
        format=reader.format,
        rel_path=rel,
        tailable=bool(getattr(reader, "tailable", False)),
    )


def read_source(
    source: MetricSource,
    *,
    since: int = 0,
    limit: int = DEFAULT_LIMIT,
    stride: int = 1,
    metric_type: str | None = None,
    key: str | None = None,
) -> SourceRead:
    """Read one source's records without writing anything.

    Args:
        source: What :func:`discover_sources` found.
        since: Records already consumed; resume after them.
        limit: Stop after this many records are collected.
        stride: Keep every *stride*-th sample **of each series**. Records
            arrive interleaved by column, so striding the flat stream would
            land on the same column every time and drop the others entirely;
            counting per series is what makes a 160k-record thermo table
            reduce to a chart-sized shape with every curve intact.
        metric_type: Keep only this record type (``scalar`` …).
        key: Keep only this series key.

    Returns:
        A :class:`SourceRead`. A reader whose dependency is missing yields an
        empty read with :attr:`SourceRead.error` set, never an exception —
        one absent library must not blank the whole chart.
    """
    from .readers import reader_for

    reader = reader_for(source.format)
    if reader is None:
        return SourceRead(source=source, error=f"no reader for {source.format!r}")

    # The viewer's policy travels down; the reader decides how cheaply to
    # honour it. Ask for one more than the limit so an exhausted source is
    # distinguishable from one the limit cut short.
    request = ReadRequest(
        since=since,
        stride=stride,
        limit=None if limit is None else limit + 1,
        metric_type=metric_type,
        keys=(key,) if key else (),
    )
    records: list[dict[str, JSONValue]] = []
    exhausted = True
    try:
        for record in reader.read(source.path, source=source.rel_path, request=request):
            if limit is not None and len(records) >= limit:
                exhausted = False
                break
            records.append(record)
    except (ImportError, OSError, ValueError) as exc:
        return SourceRead(
            source=source,
            records=records,
            cursor=since + len(records),
            error=f"{type(exc).__name__}: {exc}",
        )
    return SourceRead(
        source=source,
        records=records,
        cursor=since + len(records),
        exhausted=exhausted,
    )


def read_sources(
    root: Path | str,
    *,
    cursors: dict[str, int] | None = None,
    limit: int = DEFAULT_LIMIT,
    stride: int = 1,
    metric_type: str | None = None,
    key: str | None = None,
) -> list[SourceRead]:
    """Read every plottable source under *root*, each from its own cursor.

    Cursors are per source, keyed by :attr:`MetricSource.rel_path`: a live WAL
    that keeps growing must not shift the position of a finished log beside
    it. *limit* applies per source, so one huge table cannot starve the rest.
    """
    positions = cursors or {}
    return [
        read_source(
            source,
            since=positions.get(source.rel_path, 0),
            limit=limit,
            stride=stride,
            metric_type=metric_type,
            key=key,
        )
        for source in discover_sources(root)
    ]


def summarize(reads: list[SourceRead]) -> list[dict[str, JSONValue]]:
    """One row per series across every source, for the chart's legend."""
    from molab.plugins.metrics.wal import _summarize_records

    merged: list[dict[str, JSONValue]] = []
    for read in reads:
        merged.extend(read.records)
    return _summarize_records(merged)


def iter_records(reads: list[SourceRead]) -> Iterator[dict[str, JSONValue]]:
    """Every record across the reads, in source order."""
    for read in reads:
        yield from read.records


__all__ = [
    "DEFAULT_LIMIT",
    "MetricSource",
    "SourceRead",
    "discover_sources",
    "iter_records",
    "read_source",
    "read_sources",
    "summarize",
]
