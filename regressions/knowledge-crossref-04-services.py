"""Public-API goldens for knowledge-crossref-04-services.

Hard-coded: a failure write-up is ``Report.harvest`` (there is no second
verb), the Report as a **file** (``knowledges/report-<run.id>.md``) whose
prose is the caller's narrative and whose source is the run, and the one
projected :class:`KnowledgeRef` row for a mounted Note. The terminal Run is
produced in-process (``run.start()`` + ``mark_failed``) — no subprocess, no
third-party runtime. The execution error is not copied into the document.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from molab.knowledge import Report
from molab.knowledge.write import mount_note
from molab.services.knowledge_context import KnowledgeRef, context_with_knowledge
from molab.workspace import Workspace
from molab.workspace.refs import ref_of


def _prose(body: str) -> str:
    """The narrative. Trailing ``- [@…]`` lines are the source edges."""
    lines = body.splitlines()
    while lines and (not lines[-1].strip() or lines[-1].startswith("- [@")):
        lines.pop()
    return "\n".join(lines).strip()


def main() -> None:
    assert importlib.util.find_spec("molab.services.run_failure") is None

    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"x": 1}, id="c0ffee00")
        marker = "knowledge-crossref-04-marker"
        with run.start() as ctx:
            (ctx.execution_dir / "error.txt").write_text(marker + "\n", encoding="utf-8")
            ctx.mark_failed(marker)

        item = Report.harvest(
            run, created_by="regression", narrative="The cutoff exceeded the box."
        )
        assert type(item) is Report
        assert item.name == f"report-{run.id}"
        assert _prose(item.read()) == "The cutoff exceeded the box."
        assert marker not in item.read()
        assert item.path.name == f"report-{run.id}.md"
        assert item.path.is_file()
        assert any(s.kind == "run" and s.ref == str(ref_of(run)) for s in item.sources)

        # A Note mounted at the workspace root projects as its own file-form row
        # (walk order is not a contract, so the golden is taken on a workspace
        # holding exactly that one document).
        graph = Workspace(root=Path(raw) / "graph-lab", name="Graph")
        graph.materialize()
        mount_note(graph, "Idea", body="# Idea\n")
        assert context_with_knowledge(graph).knowledge == [
            KnowledgeRef(path="knowledges/idea.md", type="Note", title="Idea", id="idea")
        ]


if __name__ == "__main__":
    main()
