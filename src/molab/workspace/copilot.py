"""Workspace Copilot — a read-only structured summary + ranked advisory next-actions.

integration.md §7.1. :func:`summarize_workspace` turns the canonical
:class:`~molab.workspace.workspace_context.WorkspaceContext` (P0.2) into a typed
:class:`WorkspaceSummary` plus a ranked list of :class:`NextAction`s.

Two hard rules from the Copilot charter:

- **Never mutates canonical state** — the summarizer is a pure function over the
  context (no I/O). The context is workspace-on-disk; this is a projection.
- **Suggested actions are separated from executed actions** — every
  :class:`NextAction` is ``advisory`` and is *never* executed here. An action that
  would mutate canonical state names the operation it would perform (``op``);
  whether that operation needs a change proposal, an approval, or nothing at all
  is a policy question owned by whoever executes it, not by this projection.

This is the deterministic summary; an LLM-conversational Copilot is a follow-up.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from molab.workspace.workspace_context import (
    HealthFlag,
    KnowledgeRef,
    RunRef,
    WorkspaceContext,
    WorkspaceRef,
)

NextActionKind = Literal[
    "diagnose_failed_run",
    "retry_failed_run",
    "review_stale_running",
    "review_orphan_artifact",
    "answer_open_question",
]

# The mutating operation (if any) executing a next-action would perform —
# read-only actions map to None. Surfaced verbatim as ``NextAction.op`` so the
# executing layer, which owns the risk policy, can classify it.
_ACTION_OP: dict[str, str | None] = {
    "diagnose_failed_run": None,
    "retry_failed_run": "run_lifecycle",
    "review_stale_running": None,
    "review_orphan_artifact": None,
    "answer_open_question": None,
}

# Health-flag severity for ranking (lower = more urgent).
_FLAG_SEVERITY: dict[str, int] = {
    "failed_run": 0,
    "stale_running": 1,
    "orphan_artifact": 2,
}


class NextAction(BaseModel):
    """An advisory, never-executed suggestion the Copilot surfaces."""

    model_config = ConfigDict(frozen=True)

    kind: NextActionKind
    target: str
    rationale: str
    op: str | None = None
    advisory: Literal[True] = True


class WorkspaceSummary(BaseModel):
    """A structured, grounded summary of a workspace's state (§7.1)."""

    model_config = ConfigDict(frozen=True)

    workspace: WorkspaceRef
    headline: str
    counts: dict[str, int]
    failed_runs: list[RunRef]
    running_runs: list[RunRef]
    health_flags: list[HealthFlag]
    open_questions: list[KnowledgeRef]
    relevant_knowledge: list[KnowledgeRef]
    next_actions: list[NextAction]


def _action(kind: NextActionKind, target: str, rationale: str) -> NextAction:
    return NextAction(
        kind=kind,
        target=target,
        rationale=rationale,
        op=_ACTION_OP.get(kind),
    )


def summarize_workspace(context: WorkspaceContext) -> WorkspaceSummary:
    """Summarize *context* into a :class:`WorkspaceSummary` — a pure read.

    Derives ranked, advisory next-actions from the context's health flags and open
    questions (``failed_run`` > ``stale_running`` > ``orphan_artifact`` >
    ``open_question``). Writes nothing.

    Args:
        context: The canonical workspace read-model to interpret.

    Returns:
        The structured summary + ranked next-actions.
    """
    counts = {
        "projects": len(context.projects),
        "experiments": len(context.experiments),
        "workflows": len(context.workflows),
        "recent_runs": len(context.recent_runs),
        "failed_runs": len(context.failed_runs),
        "running_runs": len(context.running_runs),
        "artifacts": len(context.artifacts),
        "knowledge": len(context.knowledge),
        "open_questions": len(context.open_questions),
        "health_flags": len(context.stale_or_missing),
    }

    next_actions: list[NextAction] = []
    for flag in sorted(context.stale_or_missing, key=lambda f: _FLAG_SEVERITY.get(f.kind, 99)):
        if flag.kind == "failed_run":
            next_actions.append(
                _action("diagnose_failed_run", flag.ref, f"run {flag.ref} failed — {flag.detail}")
            )
            next_actions.append(
                _action(
                    "retry_failed_run", flag.ref, f"retry failed run {flag.ref} (requires approval)"
                )
            )
        elif flag.kind == "stale_running":
            next_actions.append(_action("review_stale_running", flag.ref, flag.detail))
        elif flag.kind == "orphan_artifact":
            next_actions.append(_action("review_orphan_artifact", flag.ref, flag.detail))
    for question in context.open_questions:
        next_actions.append(
            _action("answer_open_question", question.path, f"open question: {question.title}")
        )

    headline = (
        f"{context.workspace.name}: {counts['projects']} projects, "
        f"{counts['recent_runs']} recent runs "
        f"({counts['failed_runs']} failed, {counts['running_runs']} running), "
        f"{counts['health_flags']} health flag(s)"
    )

    return WorkspaceSummary(
        workspace=context.workspace,
        headline=headline,
        counts=counts,
        failed_runs=list(context.failed_runs),
        running_runs=list(context.running_runs),
        health_flags=list(context.stale_or_missing),
        open_questions=list(context.open_questions),
        relevant_knowledge=list(context.knowledge),
        next_actions=next_actions,
    )


__all__ = [
    "NextAction",
    "NextActionKind",
    "WorkspaceSummary",
    "summarize_workspace",
]
