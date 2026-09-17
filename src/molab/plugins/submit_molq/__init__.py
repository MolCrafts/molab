"""molq submission plugin for ``molab run``.

Provides generic molq-backed scheduler submission via
``molab run --scheduler <name>``.

The host extra :class:`MolqPlugin` publishes ``ctx.jobs`` when mounted on
``compose_*(extra=…)``. The face constructs it and hands it to the
composer; the host never imports this package.
"""

from molab.plugins.submit_molq.host import MolqJobs, MolqPlugin

__all__ = ["MolqJobs", "MolqPlugin"]
