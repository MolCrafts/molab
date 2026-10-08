"""arch-own-06f: workspace no longer carries knowledge vocabulary.

Public API only. Hard-coded goldens. No third-party runtime.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from molab.knowledge import Note
from molab.server.schemas.workspace_context import WorkspaceContextResponse
from molab.server.schemas.workspace_copilot import WorkspaceSummaryResponse
from molab.services.copilot import summarize_workspace
from molab.services.knowledge_context import KnowledgeContext, KnowledgeRef, context_with_knowledge
from molab.workspace import Run, Workspace, WorkspaceContext
from molab.workspace.validate import validate_workspace


def main() -> None:
    import molab.workspace as workspace

    assert not hasattr(workspace, "KnowledgeRef")
    assert importlib.util.find_spec("molab.workspace.copilot") is None
    assert {"knowledge", "open_questions"}.isdisjoint(WorkspaceContext.model_fields)
    assert not hasattr(Run, "NON_CONCEPT_SUBDIRS")

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "ws"
        ws = Workspace(root, name="Lab")
        ws.materialize()
        Note(root, "Idea").write("# Idea\n")
        ctx = context_with_knowledge(ws)
        assert isinstance(ctx, KnowledgeContext)
        assert ctx.knowledge == [
            KnowledgeRef(path="knowledges/idea.md", type="Note", title="Idea", id="idea")
        ]
        assert "open_questions" not in KnowledgeContext.model_fields
        summary = summarize_workspace(ctx)
        assert summary.counts["knowledge"] == 1
        assert "open_questions" not in summary.counts

        (root / "leftover").mkdir()
        run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        (Path(str(run.run_dir)) / "knowledges").mkdir()
        report = validate_workspace(ws)
        assert report.ok, report.violations
        (Path(str(run.run_dir)) / "executions" / "e01" / "leftover").mkdir(parents=True)
        flagged = validate_workspace(ws)
        stray = [item for item in flagged.violations if item.rule == "layout.stray"]
        assert len(stray) == 1
        assert stray[0].path.endswith("executions/e01/leftover")

    assert set(WorkspaceContextResponse.model_fields) == {
        "workspace",
        "focus",
        "projects",
        "experiments",
        "workflows",
        "recentRuns",
        "failedRuns",
        "runningRuns",
        "artifacts",
        "knowledge",
        "staleOrMissing",
    }
    assert set(WorkspaceSummaryResponse.model_fields) == {
        "workspace",
        "headline",
        "counts",
        "failedRuns",
        "runningRuns",
        "healthFlags",
        "relevantKnowledge",
        "nextActions",
    }
    print("arch-own-06f-sever: ok")


if __name__ == "__main__":
    main()
