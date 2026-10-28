"""Shared display helpers for run-status views.

Single canonical home for the small read/format helpers that the
full-screen dashboards need — :mod:`molab.cli.tui.run_monitor` (molq dashboard
adapter) and :mod:`molab.cli.tui` (interactive tree explorer) both
consume these instead of carrying drifting copies.

Both helpers are deliberately display-tolerant: a missing or malformed
run record / timestamp renders as blank rather than crashing the UI.
Failures are still surfaced on the debug log so they remain diagnosable.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePath

from mollog import get_logger

from molab._typing import JSONValue

logger = get_logger(__name__)


def elapsed(started: str | None, finished: str | None = None) -> str | None:
    """Compute a human-readable elapsed time from ISO timestamps.

    Canonical format: ``"42s"`` / ``"3m04s"`` / ``"12h27m56s"`` — compact,
    no spaces, every coarser unit keeps the finer ones so the hours form
    still carries its seconds rather than truncating to minutes.

    Args:
        started: ISO start timestamp (``None`` → no display).
        finished: ISO end timestamp; ``None`` means "still running"
            and the wall clock is used instead.

    Returns:
        The formatted duration, or ``None`` when *started* is missing
        or either timestamp cannot be parsed (display-tolerant).
    """
    if not started:
        return None
    try:
        start = datetime.fromisoformat(started)
        end = datetime.fromisoformat(finished) if finished else datetime.now()
        secs = max(0, int((end - start).total_seconds()))
        if secs < 60:
            return f"{secs}s"
        m, s = divmod(secs, 60)
        if m < 60:
            return f"{m}m{s:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m{s:02d}s"
    except Exception:
        logger.debug(f"elapsed: unparseable timestamps started={started!r} finished={finished!r}")
        return None


def read_run_record(run_dir: Path | PurePath) -> dict[str, JSONValue]:
    """Load the canonical zone of *run_dir*'s ``index.md`` without constructing a Run.

    Returns an empty dict when the record is missing or unreadable
    (display-tolerant); read/parse failures are logged at debug level.
    """
    from molab.workspace.entity_record import read_record
    from molab.workspace.fs_local import LocalFileSystem

    try:
        record = read_record(LocalFileSystem(), str(Path(run_dir)))
    except Exception:
        logger.debug(f"read_run_record: failed to read {run_dir}", exc_info=True)
        return {}
    return dict(record.canonical) if record is not None else {}


__all__ = ["elapsed", "read_run_record"]
