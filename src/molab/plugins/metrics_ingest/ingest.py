"""Ingest foreign run logs into a run's host metrics buffer.

A molab **Run is a host**, not a MolRec record: ``run.json`` + run-root ``alive``
are not molrec ``meta`` / ``status``, and nothing here writes those sections.
Scientific packages follow the external molrec spec; molab does not re-host it.

What this module produces is the run-local **metrics surface**: JSONL WAL
(``out/metrics.mlp.jsonl``) via :class:`~molab.plugins.metrics.MetricsWriter`.
Foreign dialects (CSV, LAMMPS, TensorBoard, event JSONL) are equal sources.

**Additive.** Source artifacts are never deleted, rewritten, moved, or
truncated — metrics are written beside them, so an unwanted ingest is undone
by removing ``out/metrics.mlp.jsonl``.

**Never fails the caller.** A converter that cannot run (missing optional
dependency, unreadable file, unmapped CSV) is recorded as a skip with its
reason and the remaining formats still ingest. Adoption of the bytes has
already happened; an ingest failure must not unwind it.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from molab._typing import JSONValue
from molab.plugins.metrics import MetricsWriter

from .detect import FormatHit, LogFormat, detect_log_formats
from .readers import ReadRequest, reader_for


@dataclass(frozen=True, slots=True)
class Skip:
    """One artifact that was not ingested, and why."""

    format: str
    """The reader's format id, as :class:`FormatHit` carries it — an open
    vocabulary, since a format belongs to whichever package can parse it."""

    path: Path
    reason: str


@dataclass(slots=True)
class IngestResult:
    """What :func:`ingest_run` did to one run directory."""

    run_dir: Path
    ingested: dict[str, int] = field(default_factory=dict)
    """Metric records written, per source format."""

    skipped: list[Skip] = field(default_factory=list)

    @property
    def records(self) -> int:
        """Total metric records written across all formats."""
        return sum(self.ingested.values())

    @property
    def did_ingest(self) -> bool:
        """True when at least one metric record was written."""
        return self.records > 0


def _relative(path: Path, root: Path) -> str:
    """Path relative to the run root, falling back to the bare name."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _records_for(hit: FormatHit, run_dir: Path) -> Iterator[dict[str, JSONValue]]:
    """Hand the file to whichever reader claimed it.

    There is no ladder of formats here on purpose: a format molab has never
    heard of ingests exactly like any other, because every one arrives through
    the same Protocol. Ingest takes the whole stream — it is persisting the
    source, so it does not get to sample it.
    """
    reader = reader_for(hit.format)
    if reader is None:
        raise ValueError(f"no reader registered for {hit.format!r}")
    return reader.read(hit.path, source=_relative(hit.path, run_dir), request=ReadRequest())


def ingest_run(
    run_dir: Path | str,
    *,
    formats: set[str] | None = None,
) -> IngestResult:
    """Turn a run's foreign logs into its host metrics buffer.

    Writes ``out/metrics.mlp.jsonl`` — no ``meta`` / ``status`` sections,
    because a Run is a host, not a record. Persisting is optional: a chart
    reads the sources directly (see :mod:`.sources`), so ingest is for when
    records should outlive the log they came from.

    Args:
        run_dir: The run root. The buffer is written under it.
        formats: Only ingest these format ids. ``None`` ingests every format a
            registered reader claims; an empty set ingests nothing.

    Returns:
        An :class:`IngestResult` with per-format record counts and every skip
        with its reason.
    """
    root = Path(run_dir)
    result = IngestResult(run_dir=root)
    writer = MetricsWriter(root)
    # The WAL this call is about to append to is itself a readable format, so
    # without excluding it a second ingest would read the file it is writing
    # and never terminate.
    destination = writer.path.resolve()

    hits = detect_log_formats(root)
    selected: list[FormatHit] = []
    for hit in hits:
        if hit.path.resolve() == destination:
            result.skipped.append(Skip(hit.format, hit.path, "this is the ingest destination"))
        elif hit.format == LogFormat.UNKNOWN:
            result.skipped.append(Skip(hit.format, hit.path, "unrecognised format — not guessed"))
        elif formats is not None and hit.format not in formats:
            result.skipped.append(Skip(hit.format, hit.path, "not selected by the operator"))
        else:
            selected.append(hit)

    if not selected:
        return result

    for hit in selected:
        try:
            written = writer.log_many(_records_for(hit, root))
        except ImportError as exc:
            result.skipped.append(Skip(hit.format, hit.path, f"dependency unavailable: {exc}"))
            continue
        except (OSError, ValueError) as exc:
            result.skipped.append(Skip(hit.format, hit.path, f"{type(exc).__name__}: {exc}"))
            continue

        if written:
            result.ingested[hit.format] = result.ingested.get(hit.format, 0) + written
        else:
            result.skipped.append(Skip(hit.format, hit.path, "no metric records found"))

    if result.did_ingest:
        writer.flush()

    return result
