"""Workspace Copilot — ``molab.services.copilot.summarize_workspace``."""

from __future__ import annotations

from molab.services.copilot import WorkspaceSummary, summarize_workspace
from molab.services.knowledge_context import KnowledgeContext, KnowledgeRef
from molab.workspace import ContextFocus, HealthFlag, RunRef, WorkspaceRef

_SUMMARY_FIELDS = (
    "workspace",
    "headline",
    "counts",
    "failed_runs",
    "running_runs",
    "health_flags",
    "relevant_knowledge",
    "next_actions",
)


def _run(run_id: str, status: str) -> RunRef:
    return RunRef(run_id=run_id, experiment_id="e", project_id="p", status=status)


def _context() -> KnowledgeContext:
    return KnowledgeContext(
        workspace=WorkspaceRef(id="lab", name="Lab", root="/tmp/lab", targets=[]),
        focus=ContextFocus(),
        recent_runs=[_run("r1", "failed"), _run("r2", "running")],
        failed_runs=[_run("r1", "failed")],
        running_runs=[_run("r2", "running")],
        knowledge=[KnowledgeRef(path="knowledges/obs.md", type="Observation", title="Obs")],
        stale_or_missing=[
            HealthFlag(kind="failed_run", ref="r1", detail="run r1 is failed (retryable)"),
            HealthFlag(kind="stale_running", ref="r2", detail="run r2 heartbeat stale"),
            HealthFlag(kind="orphan_artifact", ref="a1", detail="asset a1 producer unresolved"),
        ],
    )


class TestSummarizeWorkspace:
    def test_returns_structured_summary_with_all_fields(self) -> None:
        ctx = _context()
        summary = summarize_workspace(ctx)
        assert isinstance(summary, WorkspaceSummary)
        for field in _SUMMARY_FIELDS:
            assert hasattr(summary, field), field
        assert summary.counts == {
            "projects": 0,
            "experiments": 0,
            "workflows": 0,
            "recent_runs": 2,
            "failed_runs": 1,
            "running_runs": 1,
            "artifacts": 0,
            "knowledge": 1,
            "health_flags": 3,
        }
        assert (
            summary.headline
            == "Lab: 0 projects, 2 recent runs (1 failed, 1 running), 3 health flag(s)"
        )
        assert summary.relevant_knowledge == ctx.knowledge
        assert len(summary.failed_runs) == 1

    def test_next_actions_ranked_most_severe_first(self) -> None:
        """failed → stale → orphan → open-question."""
        actions = summarize_workspace(_context()).next_actions
        kinds = [a.kind for a in actions]
        assert kinds == [
            "diagnose_failed_run",
            "retry_failed_run",
            "review_stale_running",
            "review_orphan_artifact",
        ]

        def _first(prefix_kinds: tuple[str, ...]) -> int:
            return next(i for i, k in enumerate(kinds) if k in prefix_kinds)

        failed_i = _first(("diagnose_failed_run", "retry_failed_run"))
        stale_i = _first(("review_stale_running",))
        orphan_i = _first(("review_orphan_artifact",))
        assert failed_i < stale_i < orphan_i
        assert actions[0].target == "r1"
        import typing

        from molab.services.copilot import NextActionKind, WorkspaceSummary

        assert "answer_open_question" not in typing.get_args(NextActionKind)
        assert "open_questions" not in WorkspaceSummary.model_fields

    def test_actions_are_advisory_and_name_the_op_they_would_perform(self) -> None:
        """Every action is advisory; only the mutating retry names an ``op``.

        Whether that op needs a proposal is the executing layer's policy, so
        this projection reports the operation and classifies nothing.
        """
        actions = summarize_workspace(_context()).next_actions
        assert all(a.advisory is True for a in actions)
        by_kind = {a.kind: a for a in actions}
        assert by_kind["retry_failed_run"].op == "run_lifecycle"
        for read_only in (
            "diagnose_failed_run",
            "review_stale_running",
            "review_orphan_artifact",
        ):
            assert by_kind[read_only].op is None

    def test_summarize_is_deterministic_and_read_only(self) -> None:
        ctx = _context()
        assert summarize_workspace(ctx) == summarize_workspace(ctx)
        # ctx is frozen — a second call cannot have mutated it
        assert ctx.failed_runs[0].run_id == "r1"
