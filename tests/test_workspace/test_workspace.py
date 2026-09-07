"""Tests for the Workspace / Project / Experiment / Run hierarchy.

Scope note — this file owns the *hierarchy-specific* behaviors: lazy
construction + materialization of a ``Workspace``, entity-vs-derived-index
separation, typed-sugar slugification, ``sync_folders`` reconciliation, and
``workflow_source`` externalization on an ``Experiment``. ``add_*`` idempotency
lives in ``test_crud_convergence.py``; run materialization in
``test_add_runs.py``; the run status lifecycle in the ``test_run_lifecycle_*``
files.
"""

import json
from pathlib import Path
from uuid import UUID

import pytest

from molexp.workspace import Workspace


class TestLegacyLibraryRemoved:
    """wsokf-11: the legacy per-scope Library stack is gone (module-gone lock)."""

    def test_library_subpackage_gone(self):
        with pytest.raises(ModuleNotFoundError):
            import molexp.workspace.library  # noqa: F401


class TestWorkspace:
    def test_construction_writes_nothing(self, tmp_path):
        """Charter law: no disk I/O in ``__init__`` — all I/O is lazy."""
        Workspace(root=tmp_path / "new", name="Lab")
        assert not (tmp_path / "new" / "workspace.json").exists()

    def test_materialize_creates_workspace_json(self, tmp_path):
        ws = Workspace(root=tmp_path, name="Lab")
        ws.materialize()
        assert (tmp_path / "workspace.json").exists()

    def test_materialize_stamps_type_on_workspace_json(self, tmp_path):
        ws = Workspace(root=tmp_path, name="Lab")
        ws.materialize()
        data = json.loads((tmp_path / "workspace.json").read_text())
        assert data["type"] == "workspace.root"
        assert ws.read_meta()["type"] == "workspace.root"

    def test_child_factory_auto_materializes(self, tmp_path):
        ws = Workspace(root=tmp_path, name="Lab")
        ws.add_project("first")
        assert (tmp_path / "workspace.json").exists()

    def test_load_preserves_identity(self, workspace):
        workspace.materialize()
        loaded = Workspace.load(workspace.root)
        assert loaded.id == workspace.id
        assert loaded.name == workspace.name

    def test_entity_metadata_has_no_child_lists(self, workspace):
        """The entity ``workspace.json`` never embeds the derived child index."""
        workspace.materialize()
        data = json.loads(Path(workspace.root / "workspace.json").read_text())
        assert "projects" not in data


class TestProject:
    def test_add_project_slugifies_display_name(self, workspace):
        proj = workspace.add_project("QM9")
        assert proj.id != "qm9"
        UUID(proj.id)  # time-ordered UUIDv7, not a slug
        assert proj.name == "QM9"

    def test_get_project_resolves_slugified_display_name(self, workspace):
        workspace.add_project("My Project")
        found = workspace.get_project("My Project")
        assert found.name == "My Project"

    def test_directory_left_by_external_tooling_is_listed(self, tmp_path):
        """The tree *is* the index, so there is nothing to reconcile.

        External tooling (rsync, an unpacked archive, a hand-written dir) can
        drop a project into ``projects/`` and ``list_projects`` sees it on the
        next call — no sync hook, no index that can disagree with disk.
        """
        ws = Workspace(tmp_path)
        ws.add_project("registered")
        orphan = tmp_path / "projects" / "orphan"
        orphan.mkdir(parents=True)
        (orphan / "project.json").write_text(
            '{"schema_version":3,"id":"orphan","name":"orphan","description":"",'
            '"owner":"","tags":[],"config":{},"created_at":"2026-04-21T12:00:00"}'
        )
        assert {p.name for p in ws.list_projects()} == {"orphan", "registered"}


class TestExperiment:
    def test_ir_workflow_source_externalized_to_workflow_json(self, project):
        """A compiled-IR ``workflow_source`` lands as a standalone ``workflow.ir.json``.

        The IR is the contract the molexp VSCode preview reads directly, so it
        must be a clean, pretty-printed file (no ``schema_version`` envelope) and
        must have a single on-disk home — stripped from the embedded
        ``experiment.json`` field, rehydrated from the file on reload.
        """
        ir = {"workflow_id": "wf", "name": "demo", "task_configs": [], "links": []}
        exp = project.add_experiment("ir-exp", workflow_source=json.dumps(ir))

        doc = Path(exp.experiment_dir) / "workflow.ir.json"
        assert doc.is_file()
        # Clean IR — directly previewable, no version-envelope pollution.
        assert json.loads(doc.read_text()) == ir
        # Single home: the embedded field is cleared in experiment.json.
        raw = json.loads((Path(exp.experiment_dir) / "experiment.json").read_text())
        assert raw["workflow_source"] is None
        # File is canonical: reload rehydrates the in-memory field from it.
        reloaded = project.get_experiment("ir-exp")
        assert json.loads(reloaded.metadata.workflow_source) == ir

    def test_non_ir_workflow_source_stays_embedded(self, project):
        """A non-JSON ``workflow_source`` (a Python path) is never externalized."""
        exp = project.add_experiment("py-exp", workflow_source="train.py")
        assert not (Path(exp.experiment_dir) / "workflow.ir.json").exists()
        raw = json.loads((Path(exp.experiment_dir) / "experiment.json").read_text())
        assert raw["workflow_source"] == "train.py"


class TestRun:
    def test_reload_rehydrates_params_and_workflow_snapshot(self, experiment):
        run = experiment.add_run(
            params={"x": 42},
            workflow_snapshot={"source": "train.py"},
        )
        reloaded = experiment.get_run(run.id)
        assert reloaded.parameters == {"x": 42}
        assert reloaded.metadata.workflow_snapshot is not None
        assert reloaded.metadata.workflow_snapshot["source"] == "train.py"
