"""Run-scoped store plugin: artifacts, events, lineage, approval."""

from __future__ import annotations

from pathlib import Path

from molexp.harness.host.context import Context
from molexp.harness.host.keys import Keys
from molexp.harness.store.file_approval_store import FileApprovalStore
from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.harness.store.file_lineage_store import FileLineageStore
from molexp.harness.store.jsonl_event_log import JsonlEventLog

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
    ) -> None:
        self._run_id = run_id
        self._run_dir = Path(run_dir)
        self._workspace_root = Path(workspace_root) if workspace_root is not None else self._run_dir

    def apply(self, ctx: Context) -> None:
        """Open stores under ``run_dir/artifacts``, ``events.jsonl``, ``approvals.json``."""
        artifact_store = FileArtifactStore(root=self._run_dir / "artifacts")
        ctx.provide(Keys.RUN_ID, self._run_id)
        ctx.provide(Keys.WORKSPACE_ROOT, self._workspace_root)
        ctx.provide(Keys.ARTIFACTS, artifact_store)
        ctx.provide(Keys.EVENTS, JsonlEventLog(path=self._run_dir / "events.jsonl"))
        ctx.provide(Keys.LINEAGE, FileLineageStore(artifact_store=artifact_store))
        ctx.provide(Keys.APPROVAL, FileApprovalStore(path=self._run_dir / "approvals.json"))
