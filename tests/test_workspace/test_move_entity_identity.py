"""Regression tests: ``move_to(..., new_name=…)`` must sync ENTITY identity.

``Folder.move_to`` (``molexp.workspace.folder``) renames the directory and
rewrites the *folder* metadata, but the entity-bearing subclasses
(:class:`~molexp.workspace.project.Project`,
:class:`~molexp.workspace.experiment.Experiment`,
:class:`~molexp.workspace.run.Run`) keep a second identity in
``_entity_metadata`` — the authoritative ``project.json`` / ``experiment.json``
/ ``run.json`` record, which their ``resolve()`` derives the on-disk path from.
A rename that leaves that entity id stale desynchronizes the whole node:

* the moved dir's entity JSON still records the OLD id/name;
* ``resolve()`` still points at the OLD basename, so the very next
  ``write_meta()`` mkdirs a stray ``<container>/<old-id>/`` holding only
  ``meta.json`` under the NEW parent;
* the new parent's derived children index is keyed by the OLD id.

Each test below pins one of those symptoms through the public API only.
"""

from __future__ import annotations

import json
from pathlib import Path

import molexp as me


def _read_json(path: Path) -> dict[str, object]:
    """Load a JSON object file (entity record or children index) as a dict."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), f"{path} must hold a top-level JSON object"
    return raw


def _ws_root(workspace: me.Workspace) -> Path:
    """The workspace's on-disk root (``Workspace`` normalizes the given root)."""
    return Path(workspace.root)


class TestMoveEntityIdentity:
    def test_experiment_move_rename_syncs_entity_json(self, tmp_path: Path) -> None:
        """The moved experiment dir's ``experiment.json`` records the NEW id/name.

        ``experiment.json`` is the authoritative record for the node; after a
        renaming move it must not still claim the old identity.
        """
        workspace = me.Workspace(tmp_path / "ws")
        proj_a = workspace.add_project("proj-a")
        proj_b = workspace.add_project("proj-b")
        experiment = proj_a.add_experiment("old-name", description="d")

        experiment.move_to(proj_b, new_name="new-name")

        entity = _read_json(
            _ws_root(workspace) / "projects/proj-b/experiments/new-name/experiment.json"
        )
        assert entity["id"] == "new-name"
        assert entity["name"] == "new-name"

    def test_experiment_move_rename_leaves_no_stray_dir(self, tmp_path: Path) -> None:
        """No ``experiments/old-name/`` dir is created under the NEW parent.

        A stale ``resolve()`` makes the post-move ``write_meta()`` mkdir a second
        directory at the old basename, holding nothing but ``meta.json``.
        """
        workspace = me.Workspace(tmp_path / "ws")
        proj_a = workspace.add_project("proj-a")
        proj_b = workspace.add_project("proj-b")
        experiment = proj_a.add_experiment("old-name", description="d")

        experiment.move_to(proj_b, new_name="new-name")

        stray = _ws_root(workspace) / "projects/proj-b/experiments/old-name"
        assert not stray.exists(), (
            f"stray dir left behind: {sorted(p.name for p in stray.iterdir())}"
        )

    def test_experiment_move_rename_updates_children_indices(self, tmp_path: Path) -> None:
        """Both parents' derived ``experiments.json`` indices reflect the rename."""
        workspace = me.Workspace(tmp_path / "ws")
        proj_a = workspace.add_project("proj-a")
        proj_b = workspace.add_project("proj-b")
        experiment = proj_a.add_experiment("old-name", description="d")

        experiment.move_to(proj_b, new_name="new-name")

        root = _ws_root(workspace)
        assert list(_read_json(root / "projects/proj-b/experiments.json")) == ["new-name"]
        assert list(_read_json(root / "projects/proj-a/experiments.json")) == []

    def test_experiment_move_rename_object_resolves_to_new_dir(self, tmp_path: Path) -> None:
        """The live object resolves to the new dir, and a fresh load sees the new id."""
        workspace = me.Workspace(tmp_path / "ws")
        proj_a = workspace.add_project("proj-a")
        proj_b = workspace.add_project("proj-b")
        experiment = proj_a.add_experiment("old-name", description="d")

        experiment.move_to(proj_b, new_name="new-name")

        expected = _ws_root(workspace) / "projects/proj-b/experiments/new-name"
        assert Path(experiment.resolve()) == expected

        reloaded = workspace.project("proj-b").experiment("new-name")
        assert reloaded.id == "new-name"

    def test_run_move_rename_syncs_entity_json(self, tmp_path: Path) -> None:
        """A renamed Run's ``run.json`` records the NEW id; no old run dir survives.

        Run dirs carry the mandatory ``run-`` prefix (``runs/run-<id>/``) and
        ``RunMetadata.id`` is a top-level ``run.json`` field.
        """
        workspace = me.Workspace(tmp_path / "ws")
        project = workspace.add_project("proj-a")
        exp_a = project.add_experiment("exp-a")
        exp_b = project.add_experiment("exp-b")
        run = exp_a.add_run(params={"x": 1}, id="r-old")

        run.move_to(exp_b, new_name="r-new")

        runs_dir = _ws_root(workspace) / "projects/proj-a/experiments/exp-b/runs"
        entity_path = runs_dir / "run-r-new/run.json"
        assert entity_path.is_file()
        assert _read_json(entity_path)["id"] == "r-new"
        assert not (runs_dir / "run-r-old").exists()

    def test_project_move_rename_syncs_entity_json(self, tmp_path: Path) -> None:
        """A Project moved across workspaces syncs ``project.json`` and leaves no stray."""
        ws1 = me.Workspace(tmp_path / "ws1")
        ws2 = me.Workspace(tmp_path / "ws2")
        project = ws1.add_project("p-old")

        project.move_to(ws2, new_name="p-new")

        root2 = _ws_root(ws2)
        entity = _read_json(root2 / "projects/p-new/project.json")
        assert entity["id"] == "p-new"
        assert entity["name"] == "p-new"
        assert not (root2 / "projects/p-old").exists()
