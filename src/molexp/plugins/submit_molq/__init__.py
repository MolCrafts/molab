"""molq submission plugin for ``molexp run``.

Provides generic molq-backed scheduler submission via
``molexp run --scheduler <name>``.

The host extra :class:`MolqPlugin` publishes ``ctx.jobs`` when mounted on
``compose_*(extra=…)``. CLI/server construct it; harness never imports this
package.
"""

from molexp.plugins.submit_molq.host import MolqJobs, MolqPlugin

__all__ = ["MolqJobs", "MolqPlugin"]
