"""``PlanWorkflowRecoverer`` — the plan pipeline's half of workflow recovery.

``molab plan`` persists its generated ``build_workflow()`` program as a
``workflow_source`` artifact under the run's harness artifact root. That is a
harness-owned on-disk format, so molab does not parse it: harness registers
this recoverer on the :mod:`molab.workflow.recovery` inversion seam and
molab asks the seam.

The script-run shape (``metadata.workflow_snapshot.entrypoint``) is molab's
own and lives in :mod:`molab.workflow.recovery`; this module never handles it.

Importing this module registers the recoverer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from molab.workflow.recovery import WorkflowRecoveryError, set_workflow_recoverer

if TYPE_CHECKING:
    from collections.abc import Callable

    from molab.harness.store.file_artifact_store import FileArtifactStore
    from molab.workflow import CompiledWorkflow, Workflow
    from molab.workspace.run import Run

__all__ = ["PlanWorkflowRecoverer"]


def _store_for(run: Run) -> FileArtifactStore:
    """Open the run's harness artifact store."""
    from molab.harness.store.file_artifact_store import FileArtifactStore
    from molab.harness.store.paths import harness_artifact_root

    return FileArtifactStore(root=harness_artifact_root(run.run_dir))


class PlanWorkflowRecoverer:
    """Compile the ``workflow_source`` artifact a plan-generated run carries."""

    def can_recover(self, run: Run) -> bool:
        """True if the run carries a ``workflow_source`` artifact.

        Cheap by seam contract: this reads the artifact index, never the
        source, and never compiles.
        """
        try:
            store = _store_for(run)
            return store.latest_by_kind("workflow_source") is not None
        except Exception:
            return False

    def recover(self, run: Run) -> CompiledWorkflow | None:
        """Compile the generated ``build_workflow()`` program, if present.

        Full builtins are intentional: the source already passed the plan
        pipeline's validators, and molcrafts imports inside task bodies
        resolve at task execution, not at ``compile()``.
        """
        from molab.harness.schemas import WorkflowSource

        store = _store_for(run)
        ref = store.latest_by_kind("workflow_source")
        if ref is None:
            return None
        source = WorkflowSource.model_validate_json(store.get(ref.id)).source
        namespace: dict[str, object] = {}
        exec(compile(source, "<plan_workflow_source>", "exec"), namespace)
        raw_builder = namespace.get("build_workflow")
        if raw_builder is None or not callable(raw_builder):
            raise WorkflowRecoveryError(
                f"run {run.id}: its workflow_source artifact defines no callable "
                "build_workflow() — the generated program is malformed"
            )
        from molab.workflow import WorkflowCompiler

        builder = cast("Callable[[], Workflow]", raw_builder)
        return WorkflowCompiler().compile(builder())


set_workflow_recoverer(PlanWorkflowRecoverer())
