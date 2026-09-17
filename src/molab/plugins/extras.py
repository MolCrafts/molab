"""Face-side science extras for ``compose_*(extra=…)``.

A host composer accepts already-built plugin objects — it never reaches
for :mod:`molab.plugins` itself. The *face* (a CLI command, a server
route) builds this tuple and hands it in, which is what keeps the host
composable and these adapters swappable.

Whoever owns the face may live above molab: the harness constructs this
tuple in its own CLI, and that import is downward and legal. The rule is
about the **host**, not about which package the face belongs to.
"""

from __future__ import annotations

from molab.plugins.metrics.host import MetricsPlugin
from molab.plugins.submit_molq.host import MolqPlugin

__all__ = ["default_science_extras"]


def default_science_extras() -> tuple[MolqPlugin, MetricsPlugin]:
    """Molq (``ctx.jobs``) then metrics seam writer. Mount last on a profile."""
    return (MolqPlugin(), MetricsPlugin())
