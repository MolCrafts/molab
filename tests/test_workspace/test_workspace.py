"""Tests for the Workspace / Project / Experiment / Run hierarchy.

Scope note — this file owns the *hierarchy-specific* behaviors: lazy
construction + materialization of a ``Workspace``, entity-vs-derived-index
separation, typed-sugar slugification, ``sync_folders`` reconciliation.
``add_*`` idempotency lives in ``test_crud_convergence.py``; run materialization in
``test_add_runs.py``; the run status lifecycle in the ``test_run_lifecycle_*``
files.
"""

import json
import shutil
from pathlib import Path
from uuid import UUID

import pytest

from molab.fs import LocalFileSystem
from molab.workspace import Experiment, GridSpace, Project, Run, Workspace
from molab.workspace.errors import AmbiguousRefError, RefNotFoundError
from molab.workspace.refs import MolabRef
from molab.workspace.workspace import set_cli_root_override
from tests.support.counting_fs import CountingFileSystem


class TestLegacyLibraryRemoved:
    """wsokf-11: the legacy per-scope Library stack is gone (module-gone lock)."""

    def test_library_subpackage_gone(self):
        with pytest.raises(ModuleNotFoundError):
            import molab.workspace.library  # noqa: F401


class TestWorkspace:
    def test_construction_mints_an_id_until_materialize(self, tmp_path):
        """A new workspace id is minted in memory. The file appears at materialize."""
        ws = Workspace(root=tmp_path / "new", name="Lab")
        assert not (tmp_path / "new" / "workspace.json").exists()
        ws.materialize()
        assert (tmp_path / "new" / "workspace.json").is_file()

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
        data = json.loads(Path(workspace.root / "workspace.json").read_text(encoding="utf-8"))
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


class TestRun:
    def test_reload_rehydrates_params(self, experiment):
        run = experiment.add_run(params={"x": 42})
        assert experiment.get_run(run.id).parameters == {"x": 42}

    def test_add_run_rejects_workflow_snapshot(self, experiment):
        with pytest.raises(TypeError):
            experiment.add_run(
                params={"x": 1},
                workflow_snapshot={"source": "train.py"},  # type: ignore[call-arg]
            )

    def test_add_runs_rejects_workflow_snapshot(self, experiment):
        with pytest.raises(TypeError):
            experiment.add_runs(
                GridSpace({"k": [1]}),
                workflow_snapshot={"source": "x"},  # type: ignore[call-arg]
            )

    def test_set_run_rejects_workflow_snapshot(self, experiment):
        run = experiment.add_run(params={"x": 1})
        with pytest.raises(TypeError):
            experiment.set_run(
                run.id,
                workflow_snapshot={"source": "x"},  # type: ignore[call-arg]
            )


def _lab(tmp_path: Path) -> tuple[Workspace, Project, Experiment, Run]:
    ws = Workspace(tmp_path / "lab", name="Lab")
    project = ws.add_project("p")
    experiment = project.add_experiment("e")
    run = experiment.add_run(id="r1", params={"k": 1})
    return ws, project, experiment, run


class TestWorkspaceFind:
    """``Workspace.find`` resolves one entity per canonical reference."""

    def test_each_kind_resolves_to_that_id(self, tmp_path: Path) -> None:
        ws, project, experiment, run = _lab(tmp_path)
        with run.start() as ctx:
            art = ctx.emit_artifact("hello", name="note.txt")
            execution_id = ctx.id
        assert execution_id == "e01"
        assert ws.find(MolabRef(project_id=project.id)).id == project.id
        assert ws.find(MolabRef(experiment_id=experiment.id)).id == experiment.id
        assert ws.find(MolabRef(experiment_id=experiment.id, run_id="r1")).id == run.id
        execution = ws.find(
            MolabRef(experiment_id=experiment.id, run_id="r1", execution_id=execution_id)
        )
        assert execution is not None
        assert execution.id == execution_id
        artifact = ws.find(MolabRef(experiment_id=experiment.id, run_id="r1", artifact_id=art.id))
        assert artifact is not None
        assert artifact.id == art.id

    def test_qualified_run_refs_distinguish_same_id(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        project = ws.add_project("p")
        exp_a = project.add_experiment("A")
        exp_b = project.add_experiment("B")
        exp_a.add_run(id="r1")
        exp_b.add_run(id="r1")
        found_a = ws.find(MolabRef(experiment_id=exp_a.id, run_id="r1"))
        found_b = ws.find(MolabRef(experiment_id=exp_b.id, run_id="r1"))
        assert isinstance(found_a, Run)
        assert isinstance(found_b, Run)
        assert found_a.experiment.id != found_b.experiment.id

    def test_str_and_model_resolve_the_same_id(self, tmp_path: Path) -> None:
        ws, _project, experiment, run = _lab(tmp_path)
        ref = MolabRef(experiment_id=experiment.id, run_id=run.id)
        assert ws.find(str(ref)).id == ws.find(ref).id

    def test_unknown_experiment_raises(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        with pytest.raises(RefNotFoundError) as exc_info:
            ws.find(MolabRef(experiment_id="missing-experiment"))
        assert exc_info.value.segment == "experiment"

    def test_copied_project_is_ambiguous(self, tmp_path: Path) -> None:
        ws, project, experiment, _run = _lab(tmp_path)
        shutil.copytree(project.path, Path(str(ws.root)) / "projects" / "copy")
        with pytest.raises(AmbiguousRefError) as exc_info:
            ws.find(MolabRef(experiment_id=experiment.id))
        candidates = exc_info.value.candidates
        assert len(candidates) == 2
        assert all(candidate == MolabRef(experiment_id=experiment.id) for candidate in candidates)

    def test_missing_execution(self, tmp_path: Path) -> None:
        ws, _project, experiment, run = _lab(tmp_path)
        with run.start():
            pass
        with pytest.raises(RefNotFoundError) as exc_info:
            ws.find(MolabRef(experiment_id=experiment.id, run_id=run.id, execution_id="e09"))
        assert exc_info.value.segment == "execution"
        assert exc_info.value.entity_id == "e09"

    def test_missing_artifact(self, tmp_path: Path) -> None:
        ws, _project, experiment, run = _lab(tmp_path)
        with run.start():
            pass
        with pytest.raises(RefNotFoundError) as exc_info:
            ws.find(MolabRef(experiment_id=experiment.id, run_id=run.id, artifact_id="missing"))
        assert exc_info.value.segment == "artifact"


class TestWorkspaceIdentity:
    """A workspace id is minted once and then read back from ``workspace.json``."""

    def test_fresh_root_mints_uuid7_name(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        ws = Workspace(root, name="My Lab")
        assert ws.id[14] == "7"
        assert len(ws.id) == 36
        assert ws.name == "My Lab"
        ws._ensure_materialized()
        payload = json.loads((root / "workspace.json").read_text())
        assert payload["id"] == ws.id

    def test_handwritten_workspace_json_is_not_rewritten(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        root.mkdir()
        raw = (
            '{"id":"test-lab","name":"Test Lab","type":"workspace.root",'
            '"created_at":"2026-01-01T00:00:00"}'
        )
        path = root / "workspace.json"
        path.write_text(raw)
        written = path.read_bytes()
        ws = Workspace(root)
        assert ws.id == "test-lab"
        ws.add_project("p")
        assert path.read_bytes() == written

    def test_two_handles_on_one_fresh_root_share_one_id(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        first = Workspace(root, name="Lab")
        second = Workspace(root, name="Lab")
        assert first.id != second.id
        first.add_project("p")
        second.add_project("q")
        disk_id = json.loads((root / "workspace.json").read_text())["id"]
        assert first.id == second.id == disk_id
        assert second.metadata.id == second.folder_metadata.id == first.id
        second.materialize()
        assert second.id == first.id
        assert json.loads((root / "workspace.json").read_text())["id"] == first.id
        second.save()
        assert second.id == first.id
        assert json.loads((root / "workspace.json").read_text())["id"] == first.id

    def test_save_keeps_persisted_id(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        first = Workspace(root, name="Lab")
        first.add_project("p")
        persisted = first.id
        handle = Workspace(root, name="Lab")
        handle._entity_metadata = handle._entity_metadata.model_copy(update={"id": "other"})
        handle.save()
        assert json.loads((root / "workspace.json").read_text())["id"] == persisted
        assert handle.id == persisted

    def test_run_constructor_rejects_workflow_snapshot(self, experiment):
        with pytest.raises(TypeError):
            Run(
                experiment=experiment,
                parameters={"x": 1},
                workflow_snapshot={"source": "x"},  # type: ignore[call-arg]
            )

    def test_new_run_json_has_no_retired_keys(self, experiment):
        run = experiment.add_run(params={"x": 1})
        payload = json.loads((Path(run.run_dir) / "run.json").read_text(encoding="utf-8"))
        for key in ("workflow_snapshot", "workflow_id", "workflow_version"):
            assert key not in payload

    def test_legacy_run_json_drops_retired_keys_on_rewrite(self, experiment):
        run = experiment.add_run(params={"x": 1})
        path = Path(run.run_dir) / "run.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        before = payload["definition_hash"]
        payload["workflow_snapshot"] = {"source": "legacy"}
        payload["workflow_id"] = "wf-old"
        payload["workflow_version"] = 3
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = experiment.get_run(run.id)
        loaded._update_metadata(target="x")
        rewritten = json.loads(path.read_text(encoding="utf-8"))
        for key in ("workflow_snapshot", "workflow_id", "workflow_version"):
            assert key not in rewritten
        assert rewritten["definition_hash"] == before


class TestWorkspaceFindAssets:
    """``molab:asset/<id>`` resolves by scope and never takes the first hit."""

    def test_scope_kind_matches_the_import_site(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        src = tmp_path / "hello.txt"
        src.write_bytes(b"hello\n")
        root_asset = ws.data_assets.import_asset("root", src, action="reference")
        project = ws.add_project("alpha")
        project_asset = project.data_assets.import_asset("proj", src, action="reference")
        experiment = project.add_experiment("sweep")
        experiment_asset = experiment.data_assets.import_asset("exp", src, action="reference")
        assert ws.find(f"molab:asset/{root_asset.id}").scope.kind == "workspace"
        assert ws.find(f"molab:asset/{project_asset.id}").scope.kind == "project"
        assert ws.find(f"molab:asset/{experiment_asset.id}").scope.kind == "experiment"

    def test_missing_asset(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        with pytest.raises(RefNotFoundError) as exc_info:
            ws.find("molab:asset/missing")
        assert exc_info.value.segment == "asset"

    def test_same_id_at_two_scopes_is_ambiguous(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        project = ws.add_project("alpha")
        src = tmp_path / "hello.txt"
        src.write_bytes(b"hello\n")
        asset = project.data_assets.import_asset("raw", src, action="copy")
        record = next(Path(project.project_dir).glob("assets/*/"))
        dest = Path(ws.root) / "assets" / record.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(record, dest)
        with pytest.raises(AmbiguousRefError) as exc_info:
            ws.find(f"molab:asset/{asset.id}")
        assert len(exc_info.value.locations) == 2
        assert set(exc_info.value.locations) == {"workspace", f"project/{project.id}"}


class TestWorkspaceAssets:
    def test_returns_the_scope_repository(self, workspace: Workspace) -> None:
        from molab.workspace.artifact_repository import AssetRepository

        assert isinstance(workspace.assets, AssetRepository)
        assert workspace.assets.scope == workspace.scope

    def test_assets_at_resolves_each_host(self, workspace: Workspace) -> None:
        project = workspace.add_project("p")
        experiment = project.add_experiment("e")
        assert workspace.assets_at(workspace.scope).scope == workspace.scope
        assert workspace.assets_at(project.scope).scope == project.scope
        assert workspace.assets_at(experiment.scope).scope == experiment.scope

    def test_unknown_project_raises(self, workspace: Workspace) -> None:
        from molab.workspace.domain import AssetScope

        with pytest.raises(RefNotFoundError):
            workspace.assets_at(AssetScope(kind="project", ids=("missing",)))

    def test_run_scope_raises(self, workspace: Workspace) -> None:
        from molab.workspace.domain import AssetScope

        with pytest.raises(ValueError):
            workspace.assets_at(AssetScope(kind="run", ids=("p", "e", "r")))

    def test_source_builds_refs_without_a_literal(self) -> None:
        import inspect

        assert "molab:" not in inspect.getsource(Workspace.assets_at)


def _materialized(tmp_path: Path, name: str) -> Workspace:
    ws = Workspace(tmp_path / name, name=name)
    ws.materialize()
    return ws


class TestWorkspaceEnclosingRoot:
    def test_finds_the_lab_from_a_run_the_root_and_a_missing_child(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        project = ws.add_project("alpha")
        experiment = project.add_experiment("sweep")
        run = experiment.add_run(params={"seed": 1})

        assert Workspace.enclosing_root(run.resolve()) == ws.root
        assert Workspace.enclosing_root(ws.root) == ws.root
        assert Workspace.enclosing_root(ws.root / "projects" / "alpha" / "notes.txt") == ws.root

    def test_outside_a_workspace_is_none(self, tmp_path: Path) -> None:
        assert Workspace.enclosing_root(tmp_path / "plain" / "x") is None

    def test_the_nearest_workspace_wins(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        inner = Path(ws.root) / "inner"
        inner.mkdir()
        (inner / "workspace.json").write_text("{}\n")

        assert Workspace.enclosing_root(inner / "sub") == inner

    def test_a_symlink_keeps_the_link_spelling(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        ws.add_project("alpha")
        link = tmp_path / "link"
        link.symlink_to(ws.root, target_is_directory=True)

        assert Workspace.enclosing_root(link / "projects" / "alpha") == link

    def test_the_cli_root_override_is_ignored(self, tmp_path: Path) -> None:
        ws_a = _materialized(tmp_path, "a")
        ws_b = _materialized(tmp_path, "b")
        set_cli_root_override(ws_a.root, explicit=True)
        try:
            assert Workspace.enclosing_root(Path(ws_b.root) / "projects") == ws_b.root
        finally:
            set_cli_root_override(None)

    def test_one_is_file_per_level_and_no_other_reads(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        project = ws.add_project("alpha")
        experiment = project.add_experiment("sweep")
        run = experiment.add_run(params={"seed": 1})
        fs = CountingFileSystem(LocalFileSystem())
        fs.reset()

        assert Workspace.enclosing_root(run.resolve(), fs=fs) == run.resolve().parents[5]

        assert fs.calls["is_file"] == 7
        assert fs.opens() == 0
        assert fs.stats() == 0
        assert fs.calls["scandir"] == 0
        assert fs.calls["exists"] == 0

    def test_an_empty_remote_dirname_probes_the_filesystem_root(self) -> None:
        import posixpath

        class _RemoteSlash:
            def __init__(self, hit: str | None) -> None:
                self.hit = hit
                self.probes: list[str] = []

            def join(self, *parts: object) -> str:
                return posixpath.join(*(str(part) for part in parts))

            def dirname(self, path: object) -> str:
                text = str(path)
                return text.rsplit("/", 1)[0] if "/" in text else "."

            def is_file(self, path: object) -> bool:
                self.probes.append(str(path))
                return str(path) == self.hit

        hit = _RemoteSlash("/opt/lab/workspace.json")
        found = Workspace.enclosing_root("/opt/lab/projects/alpha", fs=hit)  # type: ignore[arg-type]
        assert str(found) == "/opt/lab"
        assert hit.probes == [
            "/opt/lab/projects/alpha/workspace.json",
            "/opt/lab/projects/workspace.json",
            "/opt/lab/workspace.json",
        ]

        missed = _RemoteSlash(None)
        assert Workspace.enclosing_root("/opt", fs=missed) is None  # type: ignore[arg-type]
        assert missed.probes == ["/opt/workspace.json", "/workspace.json"]


class TestWorkspaceMachineDir:
    def test_keeps_the_caller_spelling_and_creates_nothing(self, tmp_path: Path) -> None:
        import inspect

        missing = tmp_path / "missing"
        found = Workspace.machine_dir(missing)
        relative = Workspace.machine_dir("rel/lab")

        assert found == Path(str(missing)) / ".molab"
        assert str(relative) == "rel/lab/.molab"
        assert not missing.exists()
        assert not Path("rel/lab/.molab").exists()
        source = inspect.getsource(Workspace.machine_dir)
        assert "_cli_root_override" not in source
        assert "Workspace(" not in source

    def test_the_cli_root_override_is_ignored(self, tmp_path: Path) -> None:
        set_cli_root_override(tmp_path / "a", explicit=True)
        try:
            assert Workspace.machine_dir(tmp_path / "b") == Path(str(tmp_path / "b")) / ".molab"
        finally:
            set_cli_root_override(None)


class TestWorkspaceListHosts:
    def test_preorder_relative_to_the_root(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        project = ws.add_project("alpha")
        experiment = project.add_experiment("sweep")
        experiment.add_run(params={"seed": 1})

        relatives = [str(host.relative_to(ws.root)) for host in Workspace.list_hosts(ws.root)]

        assert relatives == [
            ".",
            "projects/alpha",
            "projects/alpha/experiments/sweep",
            "projects/alpha/experiments/sweep/runs/seed=1",
        ]

    def test_an_empty_workspace_yields_only_the_root(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")

        assert list(Workspace.list_hosts(ws.root)) == [ws.root]

    def test_projects_are_sorted_by_name(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        ws.add_project("b")
        ws.add_project("a")

        relatives = [str(host.relative_to(ws.root)) for host in Workspace.list_hosts(ws.root)]

        assert relatives.index("projects/a") < relatives.index("projects/b")

    def test_files_and_dot_directories_are_skipped(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        projects = Path(ws.root) / "projects"
        projects.mkdir()
        (projects / "README.md").write_text("hi\n")
        (projects / ".trash").mkdir()

        names = [Path(str(host)).name for host in Workspace.list_hosts(ws.root)]

        assert "README.md" not in names
        assert ".trash" not in names

    def test_a_directory_without_project_json_is_yielded(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        raw = Path(ws.root) / "projects" / "raw"
        raw.mkdir(parents=True)

        relatives = [str(host.relative_to(ws.root)) for host in Workspace.list_hosts(ws.root)]

        assert "projects/raw" in relatives

    def test_a_symlink_root_keeps_its_spelling(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        ws.add_project("alpha")
        link = tmp_path / "link"
        link.symlink_to(ws.root, target_is_directory=True)

        assert all(str(host).startswith(str(link)) for host in Workspace.list_hosts(link))

    def test_the_cli_root_override_is_ignored(self, tmp_path: Path) -> None:
        ws_a = _materialized(tmp_path, "a")
        ws_a.add_project("from-a")
        ws_b = _materialized(tmp_path, "b")
        ws_b.add_project("from-b")
        set_cli_root_override(ws_a.root, explicit=True)
        try:
            hosts = list(Workspace.list_hosts(ws_b.root))
        finally:
            set_cli_root_override(None)

        assert hosts[0] == ws_b.root
        assert all(not str(host).startswith(str(ws_a.root)) for host in hosts)

    def test_listing_is_scandir_only(self, tmp_path: Path) -> None:
        ws = _materialized(tmp_path, "lab")
        for project_name in ("a", "b"):
            project = ws.add_project(project_name)
            experiment = project.add_experiment("e")
            experiment.add_run(params={"seed": 1})
            experiment.add_run(params={"seed": 2})
        fs = CountingFileSystem(LocalFileSystem())
        fs.reset()

        list(Workspace.list_hosts(ws.root, fs=fs))

        assert fs.calls["scandir"] == 5
        assert fs.opens() == 0
        assert fs.probes() == 0
        assert fs.stats() == 0
        assert all(
            kwargs.get("with_stat") is False
            for _name, _path, kwargs in fs.log
            if _name == "scandir"
        )
