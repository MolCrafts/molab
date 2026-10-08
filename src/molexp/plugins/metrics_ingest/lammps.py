"""LAMMPS thermo tables → metric records, through molpy's metric reader.

``molpy.io.lammps.LammpsLogMetricReader`` owns the LAMMPS log end to end:
whether a file is a log with a thermo table (``sniff``, decided by
``molrs.io.lammps.is_lammps_log``) and which record each thermo cell becomes
(``read``, parsed by ``molrs.io.read_lammps_log``). molexp neither sniffs nor
parses a log itself. The import is lazy so ``import molexp`` stays light.

The reader emits one compact-key record per (thermo row, non-step column):
the column name verbatim under ``lammps/``, the step in ``s``, and the tags
``run_index`` (one per ``run`` block), ``source`` and
``wall_time_source: "ingest"`` — LAMMPS records steps, not timestamps, so
``w`` is the stamp-at-write time, never a measurement.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from molexp._typing import JSONValue

if TYPE_CHECKING:
    from molpy.io.lammps import LammpsLogMetricReader


def _metric_reader() -> LammpsLogMetricReader:
    from molpy.io.lammps import LammpsLogMetricReader

    return LammpsLogMetricReader()


def is_lammps_log(path: Path) -> bool:
    """True when *path* is a LAMMPS log that contains a thermo table.

    The banner alone is not enough: a log whose run never reached a thermo
    section has nothing to convert. A file that cannot be read is not a log.
    """
    try:
        return _metric_reader().sniff(path)
    except OSError:
        return False


def thermo_records(path: Path, *, source: str) -> Iterator[dict[str, JSONValue]]:
    """Yield the metric records of every thermo table in the log at *path*.

    Args:
        path: LAMMPS log file.
        source: The log's path relative to the run, tagged on every record.
    """
    yield from _metric_reader().read(path, source=source)
