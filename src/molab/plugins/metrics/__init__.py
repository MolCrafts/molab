"""MolPlot host-metrics plugin — the ``*.mlp.*`` surface of a run.

Owns the molplot filename contract (:mod:`.mlp_names`) and the JSONL WAL
writer / reader (:mod:`.wal`). A molab Run is a **host**, not a MolRec
record; the only metrics persist surface is ``out/<stem>.mlp.jsonl``,
and leftover ``*.mlp.zarr/`` / ``*.mlp.index.json`` are ignored.

Importing this package registers the writer factory on
:mod:`molab.workspace.metrics_seam`, which is how
``RunContext.register_metric`` / ``ctx.metrics`` reach the writer without
workspace importing plugins. ``molab/__init__`` performs that import, so any
``import molab`` process is wired.
"""

from collections.abc import Callable
from pathlib import Path

from molab.plugins.metrics.mlp_names import (
    DEFAULT_MLP_STEM,
    MLP_INDEX_SUFFIX,
    MLP_JSONL_SUFFIX,
    MLP_VL_SUFFIX,
    MLP_ZARR_SUFFIX,
    is_mlp_index,
    is_mlp_jsonl,
    is_mlp_metrics_surface,
    is_mlp_plot_surface,
    is_mlp_vl,
    is_mlp_zarr,
    mlp_index_name,
    mlp_jsonl_name,
    mlp_zarr_name,
)
from molab.plugins.metrics.wal import (
    MetricReadResult,
    MetricRecord,
    MetricsWriter,
    discover_mlp_jsonl,
    has_metrics,
    has_metrics_wal,
    read_run_metrics,
    validate_record,
)
from molab.workspace.metrics_seam import set_metrics_writer_factory


def _writer_factory(run_dir: Path, append: Callable[[str | Path, str], object]) -> MetricsWriter:
    return MetricsWriter(run_dir, append=append)


set_metrics_writer_factory(_writer_factory)

__all__ = [
    "DEFAULT_MLP_STEM",
    "MLP_INDEX_SUFFIX",
    "MLP_JSONL_SUFFIX",
    "MLP_VL_SUFFIX",
    "MLP_ZARR_SUFFIX",
    "MetricReadResult",
    "MetricRecord",
    "MetricsWriter",
    "discover_mlp_jsonl",
    "has_metrics",
    "has_metrics_wal",
    "is_mlp_index",
    "is_mlp_jsonl",
    "is_mlp_metrics_surface",
    "is_mlp_plot_surface",
    "is_mlp_vl",
    "is_mlp_zarr",
    "mlp_index_name",
    "mlp_jsonl_name",
    "mlp_zarr_name",
    "read_run_metrics",
    "validate_record",
]
