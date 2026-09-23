"""Public-API goldens for knowledge-crossref-05-harness.

Hard-coded: the two agent kinds resolve through the workspace-owned ``meta.json``
type table (and **no longer** through the knowledge concept-type registry), a
``meta.json``-only agent directory rebuilds as ``Agent`` / ``AgentSession``,
``ChangeProposal.SourceRef`` is knowledge's own class object, the Finding writer
locates its Observation through ``folder(host, name, of)`` and links with
``.ref``, ``harvest_run`` lives in ``molab.knowledge.harvest``, and a real
terminal Run harvests to ``knowledges/finding-<run.id>.md``.

The terminal Run is produced in-process (``run.start()`` + ``mark_succeeded``)
— no subprocess, no third-party runtime. The ``knowledge.created`` history
commit is in-process best-effort, so the assertions are on the returned item,
never on git state.
"""

from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

from molab.harness.agent.folders import AGENT_KIND, AGENT_SESSION_KIND, Agent, AgentSession
from molab.harness.schemas import change_proposal
from molab.harness.services.plan_runtime import record
from molab.knowledge import Finding, SourceRef
from molab.knowledge.harvest import harvest_run
from molab.knowledge.types import resolve_concept_type
from molab.workspace import Folder, Workspace
from molab.workspace.folder import class_for_folder_type, concept_from_dir


def _write_marker(directory: Path, type_str: str, marker_id: str) -> Path:
    """A ``meta.json``-only concept directory (no class-named entity JSON)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "meta.json").write_text(
        json.dumps({"type": type_str, "id": marker_id}), encoding="utf-8"
    )
    return directory


def main() -> None:
    # The workspace owns the meta.json type table; the agent kinds live there,
    # so the knowledge registry no longer answers for them.
    assert class_for_folder_type(AGENT_KIND) is Agent
    assert class_for_folder_type(AGENT_SESSION_KIND) is AgentSession
    assert resolve_concept_type(AGENT_KIND, Folder, base=Folder) is Folder
    assert resolve_concept_type(AGENT_SESSION_KIND, Folder, base=Folder) is Folder

    # One class object, no mirror type.
    assert change_proposal.SourceRef is SourceRef

    # The harness knowledge call sites name molab.knowledge.
    assert harvest_run.__module__ == "molab.knowledge.harvest"
    finding_src = inspect.getsource(record.write_finding_record)
    assert ".ref(" in finding_src
    assert "append_link" not in finding_src
    assert "knowledge_dir" not in finding_src
    record_src = inspect.getsource(record)
    assert "molab.workspace.knowledge" not in record_src
    assert "from molab.knowledge.write import write_knowledge" in record_src

    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()

        # A meta.json-only agent dir (never an agent.json) rebuilds typed.
        agent_dir = _write_marker(Path(workspace.root) / "alpha", AGENT_KIND, "alpha")
        agent = concept_from_dir(str(agent_dir), workspace)
        assert type(agent) is Agent
        session_dir = _write_marker(agent_dir / "s1", AGENT_SESSION_KIND, "s1")
        session = concept_from_dir(str(session_dir), agent)
        assert type(session) is AgentSession
        assert not (agent_dir / "agent.json").exists()

        # A real terminal run harvests into a hard-coded file name.
        experiment = workspace.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"x": 1}, id="c0ffee00")
        with run.start() as ctx:
            ctx.mark_succeeded()

        item = harvest_run(run, Finding, narrative="the run converged", created_by="regression")
        assert type(item) is Finding
        assert item.name == f"finding-{run.id}"
        assert item.path.name == f"finding-{run.id}.md"
        assert item.path.is_file()
        assert any(s.kind == "run" and s.ref == run.id for s in item.sources)


if __name__ == "__main__":
    main()
