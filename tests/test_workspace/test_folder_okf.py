"""OKF capabilities on ``workspace.Folder`` (wsokf-01/02/03).

Every Folder gains a narrative ``index.md`` whose markdown links are the
knowledge graph (``out_edges`` / ``links``). Workspace / Project / Experiment
/ Run stamp ``type`` on their entity JSON. Notes and other generic Folders
use ``meta.json``. Run hot state lives on ``run.json`` (not an ``ops/`` sidecar).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from molexp.workspace import Workspace


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

    def test_out_edges_resolves_in_tree_and_classifies_external(self, tmp_path: Path) -> None:
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        alpha = ws.add_project("alpha")
        beta = ws.add_project("beta")
        rel = os.path.relpath(str(beta.resolve()), str(alpha.resolve()))

        alpha.write_index(
            f"# Alpha\n\n- [to-beta]({rel})\n- [ext](https://example.com)\n- [nowhere](./nope)\n"
        )

        edges = {os.path.normpath(e) for e in alpha.out_edges()}
        assert os.path.normpath(str(beta.resolve())) in edges

        scan = alpha.links()
        assert any("example.com" in e for e in scan.external)
        assert any("nope" in o for o in scan.other)

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
        assert not hasattr(proj, "fs")
