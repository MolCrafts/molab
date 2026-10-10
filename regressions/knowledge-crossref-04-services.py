"""Public-API goldens for knowledge-crossref-04-services.

Hard-coded: the shared knowledge binding (``run_failure.harvest_run`` is
``molab.knowledge.harvest.harvest_run``), the failure Report as a **file**
(``knowledges/failure-analysis-<run.id>.md``) with its ``run`` source, and the
one projected :class:`KnowledgeRef` row for a mounted Note. The terminal Run is
produced in-process (``run.start()`` + ``mark_failed``) — no subprocess, no
third-party runtime.
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

from molab.knowledge import Report
from molab.knowledge.write import mount_note
from molab.services import run_failure
from molab.services.knowledge_context import KnowledgeRef, context_with_knowledge
from molab.services.run_failure import analyze_run_failure
from molab.workspace import Workspace
from molab.workspace.refs import ref_of


def main() -> None:
    # The failure Report is knowledge's own harvest, not a services writer.
    assert run_failure.Report is Report
    assert "Report.harvest(" in inspect.getsource(analyze_run_failure)

    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"x": 1}, id="c0ffee00")
        marker = "knowledge-crossref-04-marker"
        with run.start() as ctx:
            (ctx.execution_dir / "error.txt").write_text(marker + "\n", encoding="utf-8")
            ctx.mark_failed(marker)

        item = analyze_run_failure(run, created_by="regression")
        assert type(item) is Report
        assert item.name == f"failure-analysis-{run.id}"
        assert marker in item.read()
        # A Knowledge document is a file: no directory, no report.json sidecar.
        assert item.path.name == f"failure-analysis-{run.id}.md"
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
