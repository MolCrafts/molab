"""Agent / AgentSession register into the workspace ``meta.json`` type table.

Their identity file is ``meta.json`` alone (no ``agent.json``), so the
*entity-filename* axis cannot rebuild them — the workspace-owned
``register_folder_type`` table is what does, and the harness claims its two
kinds there instead of in the knowledge concept-type registry.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from molab.harness.agent import folders as agent_folders
from molab.harness.agent.folders import AGENT_KIND, AGENT_SESSION_KIND, Agent, AgentSession
from molab.knowledge.types import resolve_concept_type
from molab.workspace import Workspace
from molab.workspace.folder import Folder, class_for_folder_type, concept_from_dir


def _marker_dir(root: Path, *parts: str, type_str: str, marker_id: str) -> Path:
    """A ``meta.json``-only agent directory (the on-disk Agent layout)."""
    child = root.joinpath(*parts)
    child.mkdir(parents=True, exist_ok=True)
    (child / "meta.json").write_text(
        json.dumps({"type": type_str, "id": marker_id}), encoding="utf-8"
    )
    return child


class TestAgentTypeRegistration:
    def test_each_kind_resolves_to_its_own_class(self) -> None:
        assert class_for_folder_type(AGENT_KIND) is Agent
        assert class_for_folder_type(AGENT_SESSION_KIND) is AgentSession

    def test_the_knowledge_registry_no_longer_claims_the_agent_kinds(self) -> None:
        assert resolve_concept_type(AGENT_KIND, Folder, base=Folder) is Folder
        assert resolve_concept_type(AGENT_SESSION_KIND, Folder, base=Folder) is Folder

    def test_module_has_zero_knowledge_dependency(self) -> None:
        assert "molab.knowledge" not in inspect.getsource(agent_folders)

    def test_concept_from_dir_rebuilds_agent_and_session(self, tmp_path: Path) -> None:
        """The workspace table alone rebuilds both kinds.

        ``folder.py`` imports nothing from ``molab.knowledge`` any more (AST-guarded
        by ``tests/test_workspace/test_folder.py``), so the workspace type table is
        not merely consulted first — it is the only registry ``concept_from_dir``
        can reach, which is why the old spy on the knowledge fallback is gone.
        """
        ws = Workspace(root=tmp_path / "lab", name="Lab")
        ws.materialize()
        agent_dir = _marker_dir(ws.root, "alpha", type_str=AGENT_KIND, marker_id="alpha")

        rebuilt = concept_from_dir(str(agent_dir), ws)
        assert isinstance(rebuilt, Agent)

        session_dir = _marker_dir(
            ws.root, "alpha", "s1", type_str=AGENT_SESSION_KIND, marker_id="s1"
        )
        session = concept_from_dir(str(session_dir), rebuilt)
        assert isinstance(session, AgentSession)

    def test_layout_is_unchanged(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab", name="Lab")
        ws.materialize()
        agent = ws.add_folder(Agent(name="alpha"))

        assert (Path(ws.root) / "alpha" / "meta.json").is_file()
        assert not (Path(ws.root) / "alpha" / "agent.json").exists()

        session = agent.add_session("s1")
        assert isinstance(session, AgentSession)
        assert [s.name for s in agent.list_sessions()] == ["s1"]
