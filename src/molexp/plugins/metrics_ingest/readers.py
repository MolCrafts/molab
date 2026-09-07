"""The registry that lets a viewer read a format nobody here knows.

molexp owns no file format, and neither does molplot. A format belongs to the
package that can parse it — molpy owns ``log.lammps``, ``*.mrec`` and
``*.mlp.jsonl`` (through molrs); another package may own something else. Each
declares a reader at install time and it becomes available everywhere:

    [project.entry-points."molcrafts.metric_readers"]
    lammps_log = "molpy.integrations.metric_readers:LammpsLogReader"

The group name is deliberately **not** ``molexp.*``: a format's owner should
not carry molexp in its metadata, and :class:`MetricReader` is a
:class:`typing.Protocol`, so a provider matches it structurally without
importing anything from here. molpy declares a molcrafts capability; molexp
and molplot consume it.

Nothing is privileged. molexp's own ``*.mlp.jsonl`` arrives through the same
registry as a raw solver log, so a chart never asks "has this been converted
yet?" — only "is there a reader for it?".

Two consumers, one seam:

* **view** — molplot streams records straight to a chart and decides the
  sampling policy: it hands the reader a :class:`ReadRequest` and the reader
  honours it, pushing ``stride`` down into the parser where it can.
* **persist** — ``ingest_run`` writes the same records into a WAL, for when
  they should outlive their source. Always optional.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mollog import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

    from molexp._typing import JSONValue

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "molcrafts.metric_readers"
"""Where a package that owns a format declares its reader."""


@dataclass(frozen=True, slots=True)
class ReadRequest:
    """What the viewer wants back. The reader honours it however it can.

    Sampling is the *viewer's* policy, not the reader's: molplot knows how
    many points a chart can show, the reader knows how to skip cheaply. So the
    request travels down, and a reader that can stride inside its parser does
    — for a 160k-record thermo table that is the difference between reading a
    file and materializing it.

    A reader that cannot push any of this down passes its raw stream through
    :func:`apply` and is done.
    """

    since: int = 0
    """Records already consumed from this source; resume after them."""

    stride: int = 1
    """Keep every *stride*-th sample **of each series**, not of the flat
    stream: records arrive interleaved by column, so striding the stream
    would land on one column every time and drop the rest."""

    limit: int | None = None
    """Stop after this many records are yielded."""

    metric_type: str | None = None
    """Keep only this record type (``scalar``, ``histogram``, …)."""

    keys: tuple[str, ...] = field(default_factory=tuple)
    """Keep only these series keys. Empty means every series."""

    def wants(self, record: dict[str, JSONValue]) -> bool:
        """True when *record* passes the type/key filters (not the sampling)."""
        if self.metric_type is not None and record.get("t") != self.metric_type:
            return False
        return not (self.keys and record.get("k") not in self.keys)


@runtime_checkable
class MetricReader(Protocol):
    """Turns one file into metric records. Owned by the format's package.

    Implement it anywhere; it is a Protocol, so nothing needs importing from
    molexp. Optional attributes a reader may also declare:

    ``patterns``
        Glob hints (``("**/log.lammps",)``) for a client deciding whether to
        offer a chart *without* opening the file. A hint, never the authority
        — :meth:`sniff` is. Keep it narrow: too broad lights up an empty chart
        on unrelated files; too narrow costs only a tab.
    ``tailable``
        True when the file grows while a run is live, so polling returns more.
    """

    @property
    def format(self) -> str:
        """Stable format id, e.g. ``"lammps_log"``. Appears in the UI and API."""

    def sniff(self, path: Path) -> bool:
        """True when *path* is this format.

        The authority: it may open the file and check its content. Returning
        True on a file the reader cannot actually read turns a detection into
        a failed read, so err towards False.
        """

    def read(
        self, path: Path, *, source: str, request: ReadRequest
    ) -> Iterator[dict[str, JSONValue]]:
        """Yield metric records for *path*, honouring *request*.

        Args:
            path: The file (or directory) :meth:`sniff` accepted.
            source: Path relative to the run, for the record's ``source`` tag.
            request: The viewer's sampling and filtering policy.

        Raises:
            ImportError: When the reader's dependency is unavailable. The
                caller reports a skip and keeps going — one absent library
                must not blank a chart that has other sources.
        """


def apply(
    request: ReadRequest, records: Iterable[dict[str, JSONValue]]
) -> Iterator[dict[str, JSONValue]]:
    """Enforce *request* over a raw record stream.

    The fallback for a reader that cannot push sampling into its parser. A
    reader that *can* should do so instead and skip this — the point of
    handing the request down is to avoid building what will be thrown away.
    """
    seen_per_series: dict[object, int] = {}
    kept = 0
    for index, record in enumerate(records):
        if index < request.since:
            continue
        if not request.wants(record):
            continue
        if request.stride > 1:
            key = record.get("k")
            position = seen_per_series.get(key, 0)
            seen_per_series[key] = position + 1
            if position % request.stride:
                continue
        yield record
        kept += 1
        if request.limit is not None and kept >= request.limit:
            return


_LOCK = threading.Lock()
_REGISTRY: dict[str, MetricReader] = {}
_LOADED = False


def register_reader(reader: MetricReader) -> None:
    """Register *reader*, replacing any reader for the same format."""
    with _LOCK:
        _REGISTRY[reader.format] = reader


def unregister_reader(format_id: str) -> None:
    """Drop the reader for *format_id* if present (tests, hot-swap)."""
    with _LOCK:
        _REGISTRY.pop(format_id, None)


def reader_for(format_id: str) -> MetricReader | None:
    """The registered reader for *format_id*, or ``None``."""
    load_readers()
    with _LOCK:
        return _REGISTRY.get(format_id)


def readers() -> tuple[MetricReader, ...]:
    """Every registered reader, in registration order."""
    load_readers()
    with _LOCK:
        return tuple(_REGISTRY.values())


def describe_readers() -> list[dict[str, object]]:
    """Every registered format, as the client-facing description of it."""
    return [
        {
            "format": reader.format,
            "patterns": list(getattr(reader, "patterns", ()) or ()),
            "tailable": bool(getattr(reader, "tailable", False)),
        }
        for reader in readers()
    ]


def sniff(path: Path) -> MetricReader | None:
    """The first reader that claims *path*, or ``None`` when none does."""
    for reader in readers():
        try:
            if reader.sniff(path):
                return reader
        except OSError:  # an unreadable file is not this reader's problem
            continue
    return None


def load_readers() -> None:
    """Populate the registry once, from the entry-point group.

    There is no bundled fallback: molexp ships no format knowledge, so a
    workspace with no reader package installed reads nothing and says so,
    rather than quietly supporting one privileged format.
    """
    global _LOADED
    with _LOCK:
        if _LOADED:
            return
        _LOADED = True
    _load_entry_points()


def reset_readers() -> None:
    """Forget every reader and allow discovery to run again (tests only)."""
    global _LOADED
    with _LOCK:
        _REGISTRY.clear()
        _LOADED = False


def _load_entry_points() -> None:
    from importlib.metadata import entry_points

    for entry in entry_points(group=ENTRY_POINT_GROUP):
        try:
            register_reader(entry.load()())
        except Exception as exc:
            logger.warning(f"metric reader {entry.name!r} failed to load: {exc}")


__all__ = [
    "ENTRY_POINT_GROUP",
    "MetricReader",
    "ReadRequest",
    "apply",
    "describe_readers",
    "load_readers",
    "reader_for",
    "readers",
    "register_reader",
    "reset_readers",
    "sniff",
    "unregister_reader",
]
