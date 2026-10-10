"""OKF capabilities on ``workspace.Folder`` (wsokf-01/02/03).

Every Folder gains a narrative ``index.md``; the markdown links in it are the
knowledge graph, read and written through ``molab.knowledge`` (``Concept.links``
/ ``append_link``) — the workspace owns the narrative access, not the edge
format. Workspace / Project / Experiment / Run stamp ``type`` on their entity
JSON. Notes and other generic Folders use ``meta.json``. Run hot state lives on
``run.json`` (not an ``ops/`` sidecar).
"""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace import Workspace


class TestFolderOKF:
    def test_index_round_trips_and_is_additive(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        proj = ws.add_project("alpha")
        assert proj.read_index() == ""  # absent → empty
        proj.write_index("# Alpha\n\nnarrative\n")
        assert proj.read_index() == "# Alpha\n\nnarrative\n"
        # additive: the project's own metadata is untouched (still listed)
        assert [p.name for p in ws.list_projects()] == ["alpha"]

    def test_meta_json_marks_concept_type_path_is_id(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        proj = ws.add_project("alpha")
        assert ws.read_meta()["type"] == "workspace.root"
        pmeta = proj.read_meta()
        assert pmeta["type"] == "workspace.project"
        run = proj.add_experiment("e").add_run()
        assert json.loads((Path(run.resolve()) / "run.json").read_text())["type"] == "workspace.run"


class TestFolderFiles:
    def test_files_is_store_on_workspace_disk(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        proj = ws.add_project("alpha")
        dest = proj.files.put("note.txt", "hello")
        assert dest.read_text() == "hello"
        assert dest.parent == Path(proj.resolve())
        assert proj._disk() is ws.fs
        assert proj.fs is ws.fs
