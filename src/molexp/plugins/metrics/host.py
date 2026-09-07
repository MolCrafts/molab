"""Duck-typed host extra: wire the mlp writer onto the workspace seam.

Does not import ``molexp.harness``. Compose mounts this by ``name`` /
``inject`` / ``apply``, same as :class:`~molexp.workspace.plugin.WorkspacePlugin`.

``ctx`` does not gain a new service key (metrics is not in the host Keys
table). Apply installs the writer factory; unload restores the previous
factory so a process that only imported ``molexp`` stays wired.
"""

from __future__ import annotations

from typing import Any

__all__ = ["MetricsPlugin"]


class MetricsPlugin:
    """Install :class:`~molexp.plugins.metrics.wal.MetricsWriter` on the seam."""

    name = "metrics"
    inject: tuple[str, ...] = ()

    def apply(self, ctx: Any) -> None:  # noqa: ANN401 — duck-typed host Context
        """Set the writer factory; restore the previous factory on unload."""
        from molexp.plugins.metrics import _writer_factory
        from molexp.workspace.metrics_seam import (
            get_metrics_writer_factory,
            set_metrics_writer_factory,
        )

        previous = get_metrics_writer_factory()
        set_metrics_writer_factory(_writer_factory)

        def _restore() -> None:
            set_metrics_writer_factory(previous)

        ctx.effect(_restore)
