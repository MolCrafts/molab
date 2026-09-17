"""Inversion seam for the plugin-provided run metrics writer.

The mlp host-metrics surface (filename contract + JSONL WAL) is owned by the
:mod:`molab.plugins.metrics` plugin. Workspace is the bottom layer and must
not import plugins, so the writer reaches :class:`~molab.workspace.run_assets.RunAssets`
through this seam — the same pattern as
:func:`molab.workspace.run.set_run_executor`. Importing
:mod:`molab.plugins.metrics` registers its factory here; ``molab/__init__``
performs that import, so any ``import molab`` process is wired.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from molab._typing import JSONValue

#: One compact WAL event (``t`` / ``k`` / ``s`` / ``w`` / ``v`` / ``tags``).
MetricRecord = dict[str, JSONValue]

#: ``append(name, line)`` lands one WAL line under ``artifacts/``.
MetricsAppend = Callable[[str | Path, str], object]


class MetricsSink(Protocol):
    """What workspace needs from a run metrics writer."""

    def scalar(
        self,
        key: str,
        value: int | float,
        step: int | float | None = None,
        *,
        wall_time: str | datetime | None = None,
        tags: dict[str, JSONValue] | None = None,
    ) -> MetricRecord: ...

    def flush(self) -> None: ...


#: ``factory(run_dir, append)`` builds the writer for one execution.
MetricsWriterFactory = Callable[[Path, MetricsAppend], MetricsSink]

_factory: MetricsWriterFactory | None = None


def get_metrics_writer_factory() -> MetricsWriterFactory | None:
    """Return the registered factory, or ``None`` if the seam is unwired."""
    return _factory


def set_metrics_writer_factory(factory: MetricsWriterFactory | None) -> None:
    """Register the writer factory, or ``None`` to unwind it.

    Called by ``molab.plugins.metrics`` on import and by
    :class:`~molab.plugins.metrics.host.MetricsPlugin` on host apply/unload.
    """
    global _factory
    _factory = factory


def create_metrics_writer(run_dir: Path, append: MetricsAppend) -> MetricsSink:
    """Build a metrics writer through the registered factory.

    Raises:
        RuntimeError: If no factory is registered — ``import molab`` (which
            wires :mod:`molab.plugins.metrics`) has not run in this process.
    """
    if _factory is None:
        raise RuntimeError(
            "no metrics writer factory registered; `import molab` wires the "
            "molab.plugins.metrics plugin onto this seam"
        )
    return _factory(run_dir, append)


__all__ = [
    "MetricRecord",
    "MetricsAppend",
    "MetricsSink",
    "MetricsWriterFactory",
    "create_metrics_writer",
    "get_metrics_writer_factory",
    "set_metrics_writer_factory",
]
