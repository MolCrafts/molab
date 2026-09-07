"""Face-side science extras for ``compose_*(extra=…)``.

Harness composers accept already-built plugin objects. CLI and server
construct this tuple; they never live inside ``molexp.harness`` (the
layer DAG forbids ``harness → plugins``).
"""

from __future__ import annotations

from molexp.plugins.metrics.host import MetricsPlugin
from molexp.plugins.submit_molq.host import MolqPlugin

__all__ = ["default_science_extras"]


def default_science_extras() -> tuple[MolqPlugin, MetricsPlugin]:
    """Molq (``ctx.jobs``) then metrics seam writer. Mount last on a profile."""
    return (MolqPlugin(), MetricsPlugin())
