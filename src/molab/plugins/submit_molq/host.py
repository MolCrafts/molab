"""Duck-typed host extra: publish ``ctx.jobs`` (molq submit / cancel).

Does not import ``molab.harness``. Compose mounts this by ``name`` /
``inject`` / ``apply``. ``apply`` itself does not import molq — submit and
cancel load the adapter modules on first use.
"""

from __future__ import annotations

from typing import Any

__all__ = ["MolqJobs", "MolqPlugin"]


class MolqJobs:
    """``ctx.jobs`` handle. Methods lazy-import the molq adapter."""

    def submit_handler(self, **kwargs: Any) -> Any:  # noqa: ANN401
        """Build a :class:`~molab.plugins.submit_molq.submit.SubmitHandler`."""
        from molab.plugins.submit_molq.submit import SubmitHandler

        return SubmitHandler(**kwargs)

    def classify_cancel(self, run: Any) -> Any:  # noqa: ANN401
        """Classify how to cancel *run* (molq / local / none)."""
        from molab.plugins.submit_molq.cancel import classify

        return classify(run)

    def try_cancel(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Attempt a clean cancel; never force."""
        from molab.plugins.submit_molq.cancel import try_cancel

        return try_cancel(*args, **kwargs)


class MolqPlugin:
    """Publish :class:`MolqJobs` as ``ctx.jobs``."""

    name = "jobs"
    inject: tuple[str, ...] = ()

    def apply(self, ctx: Any) -> None:  # noqa: ANN401 — duck-typed host Context
        """Provide the jobs handle. Unload drops the key."""
        ctx.provide("jobs", MolqJobs())
