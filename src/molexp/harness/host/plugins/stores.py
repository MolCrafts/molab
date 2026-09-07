"""Run-scoped store plugin: artifacts, events, lineage, approval."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from molexp.harness.host.context import Context
from molexp.harness.host.keys import Keys
from molexp.harness.store.file_approval_store import FileApprovalStore
from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.harness.store.file_lineage_store import FileLineageStore
from molexp.harness.store.jsonl_event_log import JsonlEventLog
from molexp.harness.store.run_approval_store import RunApprovalStore

if TYPE_CHECKING:
    from molexp.workspace.execution_context import ExecutionContext

__all__ = ["RunStoresPlugin"]


class RunStoresPlugin:
    """Publish the four run-local stores onto the host.

    ``workspace_root`` is the Stage-facing root (plan: the run dir; curate:
    the real workspace root). Store files always live under *run_dir*.

    File store objects have no ``close``. ``unload`` drops the service keys only.
    """

    name = "run_stores"
    inject: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        workspace_root: Path | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> None:
        self._run_id = run_id
        self._run_dir = Path(run_dir)
        self._workspace_root = Path(workspace_root) if workspace_root is not None else self._run_dir
        self._execution_context = execution_context

    def apply(self, ctx: Context) -> None:
        """Publish stores scoped to the selected physical Execution."""
        if self._execution_context is None:
            # Non-scientific scratch profiles (currently one-shot chat and
            # config inspection) never publish these refs as MolExp Artifacts.
            storage_dir = self._run_dir
            artifact_store = FileArtifactStore(root=storage_dir / "scratch-artifacts")
            approval_store = FileApprovalStore(path=storage_dir / "approvals.json")
        else:
            storage_dir = self._execution_context.execution_dir
            artifact_store = FileArtifactStore.for_execution(self._execution_context)
            approval_store = RunApprovalStore(
                self._execution_context.run.run_dir,
                run_id=self._run_id,
                execution_id=self._execution_context.id,
            )
        ctx.provide(Keys.RUN_ID, self._run_id)
        ctx.provide(Keys.WORKSPACE_ROOT, self._workspace_root)
        ctx.provide(Keys.ARTIFACTS, artifact_store)
        ctx.provide(Keys.EVENTS, JsonlEventLog(path=storage_dir / "events.jsonl"))
        ctx.provide(Keys.LINEAGE, FileLineageStore(artifact_store=artifact_store))
        ctx.provide(Keys.APPROVAL, approval_store)
