"""``ctx.workflow`` — compile/execute handle. Methods lazy-import the engine."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from molab.harness.host.context import Context
from molab.harness.host.keys import Keys

if TYPE_CHECKING:
    from molab.workflow.protocols import RunContextLike

__all__ = ["WorkflowHandle", "WorkflowPlugin"]


class WorkflowHandle:
    """Facade over :class:`~molab.workflow.WorkflowRuntime`.

    Importing this module does not load ``molab.workflow``. Methods do.
    """

    async def execute(
        self,
        compiled: object,
        *,
        persist: bool = True,
        run_dir: str | Path | None = None,
        scratch_root: str | Path | None = None,
        seed_outputs: Mapping[str, Any] | None = None,
        run_context: RunContextLike | None = None,
        execution_id: str | None = None,
        bypass_cache: bool = False,
    ) -> object:
        """Run *compiled* and return a :class:`~molab.workflow.WorkflowResult`."""
        from molab.workflow import WorkflowRuntime
        from molab.workflow.compiled import CompiledWorkflow

        if not isinstance(compiled, CompiledWorkflow):
            raise TypeError("compiled must be a CompiledWorkflow")
        return await WorkflowRuntime().execute(
            compiled,
            persist=persist,
            run_dir=run_dir,
            scratch_root=scratch_root,
            seed_outputs=seed_outputs,
            run_context=run_context,
            execution_id=execution_id,
            bypass_cache=bypass_cache,
        )


class WorkflowPlugin:
    """Publish :class:`WorkflowHandle` as ``ctx.workflow``."""

    name = "workflow"
    inject: tuple[str, ...] = ()

    def apply(self, ctx: Context) -> None:
        """Provide :data:`Keys.WORKFLOW`."""
        ctx.provide(Keys.WORKFLOW, WorkflowHandle())
