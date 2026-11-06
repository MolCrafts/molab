"""Output markers a task returns so the engine can register them.

A task writes files under ``ctx.workdir`` and never touches the workspace.
To register one of those files (or a metric) the body returns a marker as
one of its output values. The engine, which still holds the execution,
does the registration:

* :class:`RegisterAsset` is registered by the engine. The recorded value is
  ``molab:asset/<id>``. A later task receives the file's path, resolved from
  that ref at bind time. The journal keeps the ref.
* :class:`RegisterMetric` appends a scalar to the attempt's metrics WAL.

Example::

    @wf.task
    async def export_lammps(ctx, system) -> dict:
        import molpy as mp

        out = ctx.workdir / "system.data"
        mp.io.write_lammps_data(out, system.to_frame())
        return {
            "data_file": ctx.register(out, title="system", mime="chemical/x-lammps-data"),
            "n_atoms": ctx.register_metric("n_atoms", system.n_atoms),
        }
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["RegisterAsset", "RegisterMetric"]


@dataclass(frozen=True)
class RegisterAsset:
    """Register a file the task wrote (under ``ctx.workdir``) as an asset.

    Attributes:
        path: The file the body wrote, typically under ``ctx.workdir``.
        title: Label of the asset. Identity is the content, not the title.
        tags: Free-form metadata attached to the asset.
        mime: Optional media type (e.g. ``"chemical/x-xyz"``).
    """

    path: Path
    title: str
    tags: dict[str, str] | None = None
    mime: str | None = None


@dataclass(frozen=True)
class RegisterMetric:
    """Record a scalar metric on the run from a task's output.

    Attributes:
        key: Metric series name (e.g. ``"n_atoms"``, ``"box_volume"``).
        value: The scalar value.
        step: Optional step / iteration index.
        tags: Free-form metadata attached to the metric record.
    """

    key: str
    value: float
    step: int | None = None
    tags: dict[str, str] | None = None
