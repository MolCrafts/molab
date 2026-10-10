"""Ingest foreign run logs into a run's host metrics buffer.

A molab **Run is a host**, not a MolRec record. Nothing here writes molrec
``meta`` / ``status`` sections. Scientific packages follow the external
molrec spec; molab does not ship a molrec module.

What these tools produce is the run-local metrics surface: a JSONL **WAL**
at ``out/metrics.mlp.jsonl``. That is what ``GET …/runs/{id}/metrics``
and the UI read. Leftover zarr / index files are ignored.

Public surface::

    from molab.plugins.metrics_ingest import detect_log_formats, ingest_run

    hits = detect_log_formats(run_dir)  # classify source logs, by content
    result = ingest_run(run_dir)  # append to metrics.mlp.jsonl

Detection never guesses: a file it cannot confirm is ``UNKNOWN`` and is left
alone. Ingestion is additive — source artifacts are never deleted, rewritten,
or moved.

**molab ships no reader.** Formats arrive through the
:class:`~molab.plugins.metrics_ingest.readers.MetricReader` Protocol, declared
by whichever package owns the format — molpy publishes ``lammps_log`` /
``mrec`` / ``mlp_jsonl`` in the ``molcrafts.metric_readers`` entry-point group.
No format is privileged, molab's own WAL included, so a chart never has to
ask whether something was converted first. See :mod:`.readers`.

All three write through
:meth:`molab.plugins.metrics.MetricsWriter.log_many`, the single-open bulk
path — roughly an order of magnitude faster than per-record appends on a large
thermo table, at flat memory.
"""

from molab.plugins.metrics_ingest.detect import (
    FormatHit,
    LogFormat,
    detect_log_formats,
    has_metrics_buffer,
)
from molab.plugins.metrics_ingest.ingest import (
    IngestResult,
    Skip,
    ingest_run,
)
from molab.plugins.metrics_ingest.readers import (
    ENTRY_POINT_GROUP,
    MetricReader,
    ReadRequest,
    describe_readers,
    reader_for,
    readers,
    register_reader,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "FormatHit",
    "IngestResult",
    "LogFormat",
    "MetricReader",
    "ReadRequest",
    "Skip",
    "describe_readers",
    "detect_log_formats",
    "has_metrics_buffer",
    "ingest_run",
    "reader_for",
    "readers",
    "register_reader",
]
