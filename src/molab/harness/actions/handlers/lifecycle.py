"""Run-lifecycle handlers — the guarded execution path for the five verbs.

Two surfaces over the same cores (vision-loop-07):

* **capability callables** (`execute_run_capability` / `resume_run_capability`
  / `rerun_run_capability` / `prune_runs_capability`) — the
  ``callable_path`` targets of the ``molab.lifecycle.*`` catalog entries,
  taking live workspace objects (in-process, like the curation ops);
* **the proposal handler** (`RunLifecycleHandler`, one payload-discriminated
  handler for the frozen ``run_lifecycle`` op — the ``asset_move`` precedent)
  — bound onto the guarded-execution registry, so a *granted* ChangeProposal
  dispatches the same cores.

Verb-domain law: every entry **reaps first** (``reap_zombie_run``), then the
narrow domains hold — ``run_execute`` starts *pending* only; ``resume`` /
``rerun`` act on *failed/cancelled* only (the shared
``workflow.execute_run`` enforces running/succeeded refusals);
``cancel`` intervenes on *running* only (``workspace.lifecycle_ops``);
``prune`` deletes execution attempts two-phase (``workspace.prune``).

**Local-only in v1 (loud).** The execute family refuses a run whose
``metadata.target`` names a non-local target: scheduler dispatch machinery is
CLI/server tier (``plugins/submit_molq`` / ``POST …/resume``) and harness must
not import it. In-process execution blocks the capability call for its
duration — the same contract as ``Run.execute`` in a user script.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from molab.harness.actions.proposal_executor import assert_within_affected_scope
from molab.harness.actions.resolve import resolve_object_ref
from molab.harness.schemas.change_proposal import ProposalOutcome

if TYPE_CHECKING:
    from molab._typing import JSONValue
    from molab.harness.actions.proposal_executor import ChangeActionRegistry
    from molab.harness.core.run_context import HarnessRunContext
    from molab.harness.schemas.change_proposal import ChangeProposal, ObjectRef
    from molab.workspace.run import Run

__all__ = [
    "RunLifecycleHandler",
    "execute_run_capability",
    "prune_runs_capability",
    "register_lifecycle_handlers",
    "rerun_run_capability",
    "resume_run_capability",
]


def _refuse_non_local(run: Run) -> None:
    """Refuse scheduler-backed runs loudly (v1 executes on this host only)."""
    from molab.workspace.targets import LOCAL_TARGET_NAME

    target = getattr(run.metadata, "target", None)
    if target and target != LOCAL_TARGET_NAME:
        raise ValueError(
            f"run {run.id} targets {target!r} — lifecycle capabilities execute "
            "in-process on this host only. Dispatch scheduler-backed runs via "
            "`molab run` or the server's POST /runs/{id}/resume|rerun."
        )


def _reap(run: Run) -> None:
    """Every verb entry reaps a zombie ``running`` before deciding (the law)."""
    from molab.workspace.run_reaper import reap_zombie_run

    reap_zombie_run(run)


def _run_status(run: Run) -> str:
    """Derive the scalar status string the lifecycle domain checks key on."""
    summary = run.status_summary
    if summary.active > 0:
        return "running"
    if summary.total == 0:
        return "pending"
    return run.executions[-1].status.value


def _summary(run: Run) -> dict[str, JSONValue]:
    return {"run": run.id, "status": _run_status(run)}


def _execute_family(
    run: Run,
    *,
    verb: str,
    allowed: tuple[str, ...],
    domain_hint: str,
    resume: bool = False,
    rerun: bool = False,
    fresh: bool = False,
) -> dict[str, JSONValue]:
    """The shared reap → refuse-non-local → domain-check → recover → execute body."""
    from molab.workflow import RunNotExecutableError

    _reap(run)
    _refuse_non_local(run)
    status = _run_status(run)
    if status not in allowed:
        raise RunNotExecutableError(
            f"{verb} acts on {'/'.join(allowed)} runs only; run {run.id} is "
            f"{status!r} — {domain_hint}"
        )
    # Importing the module registers harness's generated-source recoverer on
    # the molab seam; the seam then dispatches over both persisted shapes.
    import molab.harness.workflow_recovery  # noqa: F401
    from molab.workflow import compiled_workflow_for_run

    run.execute(compiled_workflow_for_run(run), resume=resume, rerun=rerun, fresh=fresh)
    return _summary(run)


def execute_run_capability(run: Run) -> dict[str, JSONValue]:
    """Start a PENDING run (verb domain: pending only)."""
    return _execute_family(
        run,
        verb="run_execute",
        allowed=("pending",),
        domain_hint="use run_resume/run_rerun for failed/cancelled, run_cancel for running.",
    )


def resume_run_capability(run: Run) -> dict[str, JSONValue]:
    """Resume a FAILED/CANCELLED run (reopen + seed completed nodes)."""
    return _execute_family(
        run,
        verb="run_resume",
        allowed=("failed", "cancelled"),
        domain_hint="pending wants run_execute, running wants run_cancel.",
        resume=True,
    )


def rerun_run_capability(run: Run, fresh: bool = False) -> dict[str, JSONValue]:
    """Rerun a FAILED/CANCELLED run from the top (``fresh`` bypasses cache read)."""
    return _execute_family(
        run,
        verb="run_rerun",
        allowed=("failed", "cancelled"),
        domain_hint="pending wants run_execute, running wants run_cancel.",
        rerun=True,
        fresh=fresh,
    )


def cancel_run_capability(run: Run) -> dict[str, JSONValue]:
    """Cancel a RUNNING run — strict intervene domain, capability signature.

    Thin wrapper over :func:`molab.workspace.lifecycle_ops.cancel_run` so the
    capability catalog's input schema (``run`` only) tracks a live signature:
    the core's operator-side seams (``signal_executor`` / ``allow_pending``)
    are shell concerns, never capability inputs.
    """
    from molab.workspace.lifecycle_ops import cancel_run

    cancel_run(run)
    return _summary(run)


def prune_runs_capability(
    run: Run,
    execution_ids: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, JSONValue]:
    """Two-phase execution prune: plan (refuses live records), then apply."""
    from molab.workspace.prune import apply_execution_prune, plan_execution_prune

    _reap(run)
    plan = plan_execution_prune(run, execution_ids=execution_ids, statuses=statuses)
    apply_execution_prune(run, plan)
    return {"run": run.id, "pruned": [entry.execution_id for entry in plan.entries]}


# ── proposal handlers (guarded execution) ────────────────────────────────────


def _sole_run_ref(proposal: ChangeProposal) -> ObjectRef:
    matches = [o for o in proposal.affected_objects if o.kind == "run"]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one 'run' in affected_objects, got {len(matches)} "
            f"(proposal {proposal.id})"
        )
    return matches[0]


def _record(
    ctx: HarnessRunContext,
    proposal: ChangeProposal,
    created_by: str,
    detail: dict[str, JSONValue],
) -> ProposalOutcome:
    ref = ctx.artifact_store.put_json(
        kind="proposal_action_result",
        obj={"proposal_id": proposal.id, "op": proposal.proposed_change.op, **detail},
        created_by=created_by,
        parent_ids=list(proposal.evidence),
    )
    return ProposalOutcome(
        status="executed",
        decided_by=created_by,
        decided_at=datetime.now(tz=UTC),
        result_artifact_ids=[ref.id],
    )


class RunLifecycleHandler:
    """Handle the ``run_lifecycle`` op — all five verbs, payload-discriminated.

    Mirrors the ``asset_move`` precedent (one :data:`HighRiskOp`, the concrete
    verb rides ``proposed_change.payload["lifecycle_verb"]``): the frozen
    HighRiskOp vocabulary already carries ``run_lifecycle``, so no vocabulary
    change is needed and ``approval_level_for`` stays reversibility-driven.
    """

    async def apply(self, ctx: HarnessRunContext, proposal: ChangeProposal) -> ProposalOutcome:
        run_ref = _sole_run_ref(proposal)
        assert_within_affected_scope(proposal, [run_ref])
        run = cast("Run", resolve_object_ref(ctx.workspace_root, run_ref))
        payload = proposal.proposed_change.payload
        verb = payload.get("lifecycle_verb")
        if verb == "execute":
            detail = execute_run_capability(run)
        elif verb == "resume":
            detail = resume_run_capability(run)
        elif verb == "rerun":
            detail = rerun_run_capability(run, fresh=bool(payload.get("fresh", False)))
        elif verb == "cancel":
            detail = cancel_run_capability(run)
        elif verb == "prune":
            detail = prune_runs_capability(
                run,
                execution_ids=cast("list[str] | None", payload.get("execution_ids")),
                statuses=cast("list[str] | None", payload.get("statuses")),
            )
        else:
            raise ValueError(
                f"run_lifecycle proposal {proposal.id} carries unknown "
                f"lifecycle_verb {verb!r} (expected execute/resume/rerun/cancel/prune)"
            )
        return _record(ctx, proposal, f"run_lifecycle.{verb}", detail)


def register_lifecycle_handlers(registry: ChangeActionRegistry) -> None:
    """Bind the ``run_lifecycle`` handler onto *registry* (alongside curation's)."""
    registry.register("run_lifecycle", RunLifecycleHandler())
