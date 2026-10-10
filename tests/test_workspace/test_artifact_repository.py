"""Unit tests for ``molab.workspace.artifact_repository``.

``TestAssetRepository`` (arch-own-02a-record): ``promote`` stamps ``asset.json`` and
``versions/vNNN.json`` with the current ``MOLAB_SCHEMA_VERSION`` like every
other workspace writer, instead of a hard-coded literal.

``TestArtifactRepositoryEmit`` and ``TestArtifactRepositoryReadBytes`` cover
recorded-path and reserved refusals (no byte write) and ``read_bytes``.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from molab.workspace import Project, Run, Workspace
from molab.workspace.artifact_repository import (
    ArtifactRepository,
    AssetRepository,
    scan_artifacts,
    scan_asset_repositories,
    walk_artifacts,
)
from molab.workspace.domain import Artifact, ArtifactOrigin, ExecutionMode, ImportOrigin
from molab.workspace.errors import UnmigratedAssetError
from molab.workspace.history import AgentRef
from molab.workspace.schema_version import MOLAB_SCHEMA_VERSION
from tests.test_workspace.asset_writer_cases import (
    ImportAssetCases,
    MigrateLegacyCases,
    RegisterInPlaceCases,
    RewriteLegacyCases,
    record_dir,
)


def _raw(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _attempt(run: Run) -> tuple[str, Path]:
    with run.start() as ctx:
        execution_id = ctx.id
    return execution_id, run.execution_dir(execution_id)


def _stage(exec_dir: Path, *parts: str, payload: bytes) -> Path:
    src = exec_dir.joinpath(*parts)
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(payload)
    return src


def _emit(
    repo: ArtifactRepository,
    source: Path,
    *,
    exec_dir: Path,
    execution_id: str,
    run: Run,
    project: Project,
    name: str,
    recorded: tuple[Artifact, ...] | None = None,
    reserved: bool | None = None,
    semantic_type: str | None = None,
) -> Artifact:
    """Call ``emit``. Omit ``recorded`` / ``reserved`` unless the test sets them."""
    kwargs: dict[str, object] = {}
    if recorded is not None:
        kwargs["recorded"] = recorded
    if reserved is not None:
        kwargs["reserved"] = reserved
    if semantic_type is not None:
        kwargs["semantic_type"] = semantic_type
    return repo.emit(
        source,
        execution_dir=exec_dir,
        execution_id=execution_id,
        run_id=run.id,
        project_id=project.id,
        created_by=AgentRef(id="t", type="system"),
        name=name,
        **kwargs,
    )


class TestAssetRepository:
    def test_promote_stamps_current_schema_version(self, project: Project, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact({"x": 1}, name="a.json")

        project.assets.promote(artifact, created_by=AgentRef(id="t", type="system"))

        asset_files = sorted((Path(project.project_dir) / "assets").glob("*/asset.json"))
        assert len(asset_files) == 1
        asset_root = asset_files[0].parent
        assert _raw(asset_root / "asset.json")["schema_version"] == MOLAB_SCHEMA_VERSION
        version_file = asset_root / "versions" / "v001.json"
        assert _raw(version_file)["schema_version"] == MOLAB_SCHEMA_VERSION


class TestArtifactRepositoryEmit:
    def test_refuses_recorded_path(self, workspace: Workspace, project: Project, run: Run) -> None:
        execution_id, exec_dir = _attempt(run)
        src = _stage(exec_dir, "work", "x.bin", payload=b"old")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        a1 = _emit(
            repo,
            src,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=project,
            name="x.bin",
        )
        src.write_bytes(b"new")

        with pytest.raises(ValueError) as raised:
            _emit(
                repo,
                src,
                exec_dir=exec_dir,
                execution_id=execution_id,
                run=run,
                project=project,
                name="x.bin",
                recorded=(a1,),
            )

        assert a1.path == "artifacts/x.bin"
        assert a1.id in str(raised.value)
        assert "artifacts/x.bin" in str(raised.value)
        promoted = (exec_dir / "artifacts" / "x.bin").read_bytes()
        assert promoted == b"old"
        assert f"sha256:{hashlib.sha256(promoted).hexdigest()}" == a1.content.digest

    def test_refuses_reserved_dir_unless_reserved(
        self, workspace: Workspace, project: Project, run: Run
    ) -> None:
        execution_id, exec_dir = _attempt(run)
        src = _stage(exec_dir, "work", "_molab", "r.json", payload=b"{}")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)

        with pytest.raises(ValueError):
            _emit(
                repo,
                src,
                exec_dir=exec_dir,
                execution_id=execution_id,
                run=run,
                project=project,
                name="r.json",
            )

        artifact = _emit(
            repo,
            src,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=project,
            name="r.json",
            reserved=True,
        )
        assert artifact.path.endswith("artifacts/_molab/r.json")

    def test_refuses_result_semantic_type_unless_reserved(
        self, workspace: Workspace, project: Project, run: Run
    ) -> None:
        execution_id, exec_dir = _attempt(run)
        src = _stage(exec_dir, "work", "x.bin", payload=b"x")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)

        with pytest.raises(ValueError):
            _emit(
                repo,
                src,
                exec_dir=exec_dir,
                execution_id=execution_id,
                run=run,
                project=project,
                name="x.bin",
                semantic_type="result",
            )

        artifact = _emit(
            repo,
            src,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=project,
            name="x.bin",
            semantic_type="result",
            reserved=True,
        )
        assert artifact.semantic_type == "result"

    def test_distinct_paths_are_allowed(
        self, workspace: Workspace, project: Project, run: Run
    ) -> None:
        execution_id, exec_dir = _attempt(run)
        src_x = _stage(exec_dir, "work", "x.bin", payload=b"x")
        src_y = _stage(exec_dir, "work", "y.bin", payload=b"y")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        a1 = _emit(
            repo,
            src_x,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=project,
            name="x.bin",
        )

        emitted = _emit(
            repo,
            src_y,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=project,
            name="y.bin",
            recorded=(a1,),
        )

        assert emitted.path.endswith("artifacts/y.bin")
        assert (exec_dir / "artifacts" / "y.bin").read_bytes() == b"y"

    def test_stores_execution_relative_path(
        self, workspace: Workspace, project: Project, run: Run
    ) -> None:
        with run.start() as ctx:
            src = ctx.get_dir("work") / "metrics.json"
            src.write_bytes(b"{}")
            artifact = ctx.emit_artifact(src, name="metrics.json")
            execution_id = ctx.id

        assert artifact.path == "artifacts/metrics.json"
        assert artifact.source_path == "work/metrics.json"
        raw = _raw(run.execution_dir(execution_id) / "execution.json")
        assert raw["artifacts"][0]["path"] == "artifacts/metrics.json"
        assert raw["artifacts"][0]["source_path"] == "work/metrics.json"


class TestArtifactRepositoryLocate:
    def test_new_form_joins_the_execution_dir(self, workspace: Workspace, run: Run) -> None:
        execution_id, exec_dir = _attempt(run)
        src = _stage(exec_dir, "work", "b.txt", payload=b"b")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        artifact = _emit(
            repo,
            src,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=run.experiment.project,
            name="b.txt",
        )
        nested = artifact.model_copy(update={"path": "artifacts/a/b.txt"})
        assert (
            Path(repo.locate(nested, execution_dir=exec_dir))
            == exec_dir / "artifacts" / "a" / "b.txt"
        )
        out_form = artifact.model_copy(update={"path": "out/task/x"})
        assert (
            Path(repo.locate(out_form, execution_dir=exec_dir)) == exec_dir / "out" / "task" / "x"
        )

    def test_legacy_form_resolves_under_the_workspace(self, workspace: Workspace, run: Run) -> None:
        execution_id, exec_dir = _attempt(run)
        src = _stage(exec_dir, "work", "b.txt", payload=b"b")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        artifact = _emit(
            repo,
            src,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=run.experiment.project,
            name="b.txt",
        )
        legacy_path = (exec_dir / "artifacts" / "b.txt").relative_to(workspace.path).as_posix()
        legacy = artifact.model_copy(update={"path": legacy_path})
        assert (
            Path(repo.locate(legacy, execution_dir=exec_dir)).resolve()
            == (workspace.path / legacy_path).resolve()
        )
        with run.start(mode=ExecutionMode.RERUN) as other:
            other_dir = run.execution_dir(other.id)
        with pytest.raises(ValueError):
            repo.locate(legacy, execution_dir=other_dir)

    def test_rejects_absolute_empty_and_parent_segments(
        self, workspace: Workspace, run: Run
    ) -> None:
        execution_id, exec_dir = _attempt(run)
        src = _stage(exec_dir, "work", "b.txt", payload=b"b")
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        artifact = _emit(
            repo,
            src,
            exec_dir=exec_dir,
            execution_id=execution_id,
            run=run,
            project=run.experiment.project,
            name="b.txt",
        )
        for bad in ("/abs/x", "", "artifacts/../../x"):
            with pytest.raises(ValueError):
                repo.locate(artifact.model_copy(update={"path": bad}), execution_dir=exec_dir)


class TestArtifactRepositoryReadBytes:
    def test_returns_emitted_bytes(self, workspace: Workspace, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"abc", name="x.bin")
            execution_id = ctx.id

        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        got = repo.read_bytes(artifact, execution_dir=run.execution_dir(execution_id))
        assert got == b"abc"

    def test_refuses_out_of_attempt_record(self, workspace: Workspace, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"abc", name="x.bin")
            execution_id = ctx.id

        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        escaped = artifact.model_copy(update={"path": "../../escape.bin"})
        with pytest.raises(ValueError):
            repo.read_bytes(escaped, execution_dir=run.execution_dir(execution_id))

        # INITIAL is only legal before any attempt exists; RERUN opens the next one.
        with run.start(mode=ExecutionMode.RERUN) as other:
            other_id = other.id
        # Legacy records store a workspace-relative path. A new-form path on
        # another attempt is Run.artifact_location's check, not this one.
        real = run.execution_dir(execution_id) / artifact.path
        legacy_path = real.relative_to(workspace.path).as_posix()
        legacy = artifact.model_copy(update={"path": legacy_path})
        with pytest.raises(ValueError):
            repo.read_bytes(legacy, execution_dir=run.execution_dir(other_id))
        got = repo.read_bytes(legacy, execution_dir=run.execution_dir(execution_id))
        assert got == b"abc"

    def test_missing_bytes_raise(self, workspace: Workspace, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"abc", name="x.bin")
            execution_id = ctx.id

        (run.execution_dir(execution_id) / artifact.path).unlink()
        repo = ArtifactRepository(workspace.path, fs=workspace.fs)
        with pytest.raises(FileNotFoundError):
            repo.read_bytes(artifact, execution_dir=run.execution_dir(execution_id))


def _rewrite_execution(
    run: Run, execution_id: str, mutate: Callable[[dict[str, object]], None]
) -> None:
    path = run.execution_dir(execution_id) / "execution.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")


class TestWalkArtifacts:
    def test_reports_entity_ids(self, project: Project) -> None:
        ws = project.workspace
        exp_a = project.add_experiment("alpha")
        exp_b = project.add_experiment("beta")
        run_a = exp_a.add_run(params={"n": "a"})
        run_b = exp_b.add_run(params={"n": "b"})
        with run_a.start() as ctx:
            ctx.emit_artifact(b"a", name="a.txt")
        with run_b.start() as ctx:
            ctx.emit_artifact(b"b", name="b.txt")

        locs = list(walk_artifacts(ws))
        assert {loc.experiment_id for loc in locs} == {exp_a.id, exp_b.id}
        assert {loc.run_id for loc in locs} == {run_a.id, run_b.id}
        assert {loc.execution_id for loc in locs} == {"e01"}
        assert all(loc.location is not None and Path(loc.location).is_file() for loc in locs)
        assert scan_artifacts(ws) == [loc.artifact for loc in walk_artifacts(ws)]

    def test_project_filter_skips_other_projects(self, workspace: Workspace) -> None:
        left_project = workspace.add_project("one")
        first = left_project.add_experiment("e").add_run()
        second = workspace.add_project("two").add_experiment("e").add_run()
        with first.start() as ctx:
            left = ctx.emit_artifact(b"a", name="a.txt")
        with second.start() as ctx:
            ctx.emit_artifact(b"b", name="b.txt")

        found = list(walk_artifacts(workspace, project_id=left_project.id))
        assert [loc.artifact.id for loc in found] == [left.id]

    def test_rejected_path_yields_no_location(self, run: Run) -> None:
        with run.start() as ctx:
            ctx.emit_artifact(b"a", name="a.txt")
            execution_id = ctx.id

        def absolute(raw: dict[str, object]) -> None:
            artifacts = raw["artifacts"]
            assert isinstance(artifacts, list)
            artifacts[0]["path"] = "/abs/x"

        _rewrite_execution(run, execution_id, absolute)
        locs = list(walk_artifacts(run.experiment.project.workspace))
        assert len(locs) == 1
        assert locs[0].location is None

    def test_foreign_run_id_yields_no_location(self, project: Project) -> None:
        exp = project.add_experiment("alpha")
        run_a = exp.add_run(params={"n": "a"})
        run_b = exp.add_run(params={"n": "b"})
        with run_a.start() as ctx:
            ctx.emit_artifact(b"a", name="a.txt")
            execution_id = ctx.id
        with run_b.start() as ctx:
            ctx.emit_artifact(b"b", name="b.txt")

        def foreign(raw: dict[str, object]) -> None:
            artifacts = raw["artifacts"]
            assert isinstance(artifacts, list)
            stolen = dict(artifacts[0])
            stolen["id"] = "01900000-0000-7000-8000-000000000099"
            stolen["run_id"] = run_b.id
            artifacts.append(stolen)

        _rewrite_execution(run_a, execution_id, foreign)
        locs = list(walk_artifacts(project.workspace))
        assert len(locs) == 3
        missing = [loc for loc in locs if loc.location is None]
        present = [loc for loc in locs if loc.location is not None]
        assert len(missing) == 1
        assert missing[0].artifact.id == "01900000-0000-7000-8000-000000000099"
        assert len(present) == 2
        assert all(Path(loc.location).is_file() for loc in present if loc.location)


class TestAssetRepositoryPromote:
    """Origin ref is the live promote contract (05c dropped ``AssetVersion.path``)."""

    def test_public_asset_dir_is_gone(self) -> None:
        assert hasattr(AssetRepository, "asset_dir") is False
        assert hasattr(AssetRepository, "_slug_of") is True

    def test_unrecorded_artifact_raises(self, project: Project, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"hi", name="a.bin")
        fake = artifact.model_copy(update={"id": "01900000-0000-7000-8000-000000000001"})
        with pytest.raises(ValueError):
            project.assets.promote(fake, created_by=AgentRef(id="t", type="system"))

    def test_promote_records_qualified_origin(self, project: Project, experiment, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"hi", name="a.bin")
        _asset, version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        assert isinstance(version.origin, ArtifactOrigin)
        assert version.origin.ref == (
            f"molab:experiment/{experiment.id}/run/{run.id}/artifact/{artifact.id}"
        )
        assert Path(project.assets.payload_path(_asset.id)).read_bytes() == b"hi"

    def test_second_experiment_qualifies_that_experiment(self, project: Project) -> None:
        project.add_experiment("one")
        exp2 = project.add_experiment("two")
        run2 = exp2.add_run(params={"seed": 2})
        artifact = _hello_artifact(run2)
        _asset, version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        assert isinstance(version.origin, ArtifactOrigin)
        assert version.origin.ref == (
            f"molab:experiment/{exp2.id}/run/{run2.id}/artifact/{artifact.id}"
        )

    def test_written_files_omit_legacy_keys(self, project: Project, run: Run) -> None:
        artifact = _hello_artifact(run)
        project.assets.promote(artifact, created_by=AgentRef(id="t", type="system"))
        asset_json = next(Path(project.project_dir).glob("assets/*/asset.json"))
        raw_asset = _raw(asset_json)
        raw_version = _raw(next(asset_json.parent.glob("versions/*.json")))
        assert raw_asset["schema_version"] == MOLAB_SCHEMA_VERSION
        assert "scope" not in raw_asset
        assert "project_id" not in raw_asset
        assert raw_version["schema_version"] == MOLAB_SCHEMA_VERSION
        assert "path" not in raw_version
        assert "source_artifact_id" not in raw_version

    def test_cross_project_promote_raises(
        self, workspace: Workspace, project: Project, run: Run
    ) -> None:
        artifact = _hello_artifact(run)
        other = workspace.add_project("other")
        with pytest.raises(ValueError):
            other.assets.promote(artifact, created_by=AgentRef(id="t", type="system"))

    def test_qualify_filters_walk_artifacts(self) -> None:
        source = inspect.getsource(AssetRepository._qualify_artifact)
        assert "walk_artifacts" in source
        assert "project_id=" in source
        for banned in ("list_experiments", "list_runs", "executions"):
            assert banned not in source
        assert not hasattr(AssetRepository, "_workspace_rel")


HELLO = b"hello\n"
HELLO_DIGEST = "sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"


def _hello_artifact(run: Run) -> Artifact:
    with run.start() as ctx:
        path = ctx.get_dir("work") / "hello.txt"
        path.write_bytes(HELLO)
        return ctx.emit_artifact(path, name="hello.txt")


class TestScanAssetRepositories:
    def test_project_and_experiment_hosts(
        self, workspace: Workspace, project: Project, experiment
    ) -> None:
        del project, experiment
        repos = scan_asset_repositories(workspace)
        assert [repo.scope.kind for repo in repos] == ["workspace", "project", "experiment"]
        source = inspect.getsource(scan_asset_repositories)
        assert "Workspace.list_hosts" in source
        assert "list_projects" not in source
        assert "list_experiments" not in source

    def test_empty_workspace_is_one_host(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "empty", name="empty")
        repos = scan_asset_repositories(ws)
        assert len(repos) == 1
        assert repos[0].scope.kind == "workspace"

    def test_a_workspace_under_a_runs_directory_keeps_the_root(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "runs" / "lab", name="lab")
        ws.materialize()
        ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})

        kinds = [repo.scope.kind for repo in scan_asset_repositories(ws)]

        assert kinds == ["workspace", "project", "experiment"]

    def test_a_hand_made_directory_without_an_entity_file_is_skipped(
        self, workspace: Workspace
    ) -> None:
        raw = Path(str(workspace.root)) / "projects" / "raw"
        raw.mkdir(parents=True)
        before = [repo.scope for repo in scan_asset_repositories(workspace)]

        after = [repo.scope for repo in scan_asset_repositories(workspace)]

        assert after == before


class TestAssetRepositoryList:
    def test_promote_copy_and_reference(self, project: Project, run: Run, tmp_path: Path) -> None:
        artifact = _hello_artifact(run)
        promoted, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        copied = project.data_assets.import_asset("raw", src, action="copy")
        referenced = project.data_assets.import_asset("ext", src, action="reference")
        listed = {item.id: item for item in project.assets.list()}
        assert set(listed) == {promoted.id, copied.id, referenced.id}
        assert listed[copied.id].title == "raw"
        assert listed[referenced.id].title == "ext"
        assert listed[copied.id].id == copied.id


class TestAssetRepositoryVersions:
    def test_copy_file(self, project: Project, tmp_path: Path) -> None:
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("greeting", src, action="copy")
        versions = project.assets.versions(asset.id)
        assert len(versions) == 1
        version = versions[0]
        assert version.version == 1
        assert isinstance(version.origin, ImportOrigin)
        assert version.origin.action == "copy"
        # 05e restates 05c's assets/<asset_id>/payload: the directory is the slug.
        assert version.origin.location == "assets/greeting/payload"
        assert version.content is not None
        assert version.content.digest == HELLO_DIGEST
        assert version.content.size == 6
        assert version.content.kind == "file"

    def test_directory_copy_sums_bytes(self, project: Project, tmp_path: Path) -> None:
        folder = tmp_path / "bundle"
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"ab")
        (folder / "b.txt").write_bytes(b"c")
        asset = project.assets.import_asset("bundle", folder, action="copy")
        content = project.assets.versions(asset.id)[0].content
        assert content is not None
        assert content.kind == "directory"
        assert content.size == 3

    def test_symlink_has_no_content(self, project: Project, tmp_path: Path) -> None:
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("link", src, action="symlink")
        assert project.assets.versions(asset.id)[0].content is None

    def test_consumed_ids(self, project: Project, tmp_path: Path) -> None:
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("child", src, action="copy", consumed=["up-1"])
        origin = project.assets.versions(asset.id)[0].origin
        assert isinstance(origin, ImportOrigin)
        assert origin.input_ids == ("up-1",)


class TestAssetRepositoryPayloadPath:
    def test_promoted_artifact_bytes(self, project: Project, run: Run) -> None:
        artifact = _hello_artifact(run)
        asset, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        assert Path(project.assets.payload_path(asset.id)).read_bytes() == HELLO

    def test_copy_resolves_under_the_project(self, project: Project, tmp_path: Path) -> None:
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("greeting", src, action="copy")
        resolved = Path(project.assets.payload_path(asset.id))
        assert resolved == Path(project.project_dir) / "assets" / "greeting" / "payload"
        assert resolved.read_bytes() == HELLO

    def test_reference_resolves_to_the_source(self, project: Project, tmp_path: Path) -> None:
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = project.assets.import_asset("ext", src, action="reference")
        assert project.assets.payload_path(asset.id) == str(src.resolve())

    def test_workspace_repository_reads_its_own_import(
        self, workspace: Workspace, tmp_path: Path
    ) -> None:
        src = tmp_path / "hello.txt"
        src.write_bytes(HELLO)
        asset = workspace.data_assets.import_asset("root", src, action="reference")
        repo = AssetRepository(workspace, workspace.scope, workspace.root)
        assert repo.get(asset.id).title == "root"

    def test_unknown_asset_raises(self, project: Project) -> None:
        with pytest.raises(KeyError):
            project.assets.payload_path("missing")

    def test_source_uses_artifact_location(self) -> None:
        source = inspect.getsource(AssetRepository.payload_path)
        assert "artifact_location" in source
        assert "execution_dir" not in source


class TestAssetRepositoryImportAsset(ImportAssetCases):
    """arch-own-05e import_asset cases. Bodies live in asset_writer_cases."""


class TestAssetRepositoryRegisterInPlace(RegisterInPlaceCases):
    """arch-own-05e register_in_place cases."""


class TestAssetRepositoryRewriteLegacy(RewriteLegacyCases):
    """arch-own-05e rewrite_legacy cases."""


class TestMigrateLegacyAssets(MigrateLegacyCases):
    """arch-own-05e migrate_legacy_assets cases."""


class TestAssetRepositoryUnmigrated:
    """A legacy record makes the whole scope unreadable until rewrite_legacy."""

    def test_data_import_record_blocks_the_scope_until_rewrite(self, tmp_path: Path) -> None:
        from tests.support.legacy_assets import LEGACY_ID, write_legacy_data_asset

        ws = Workspace(tmp_path / "lab", name="lab")
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        unified = ws.data_assets.import_asset("greeting", source)
        payload = b"legacy\n"
        write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=payload,
            source_path="/data/legacy.bin",
        )
        with pytest.raises(UnmigratedAssetError) as listed:
            ws.assets.list()
        assert listed.value.reason == "data-import record"
        assert listed.value.path.endswith(f"assets/{LEGACY_ID}/asset.json")
        assert "molab migrate assets" in str(listed.value)
        assert str(ws.root) in str(listed.value)
        with pytest.raises(UnmigratedAssetError):
            ws.assets.get(LEGACY_ID)
        with pytest.raises(UnmigratedAssetError):
            ws.assets.get(unified.id)
        with pytest.raises(UnmigratedAssetError):
            ws.assets._slug_of(LEGACY_ID)

        ws.assets.rewrite_legacy()
        assert len(ws.assets.list()) == 2
        assert ws.assets.get(LEGACY_ID).title == "legacy-data"
        version = ws.assets.versions(LEGACY_ID)[0]
        assert version.id == f"{LEGACY_ID}-v001"
        assert version.version == 1
        assert isinstance(version.origin, ImportOrigin)
        assert version.origin.kind == "import"
        assert version.origin.action == "copy"
        assert version.origin.location == f"assets/{LEGACY_ID}/payload"
        assert version.origin.uri == "/data/legacy.bin"
        assert version.content is None
        assert Path(ws.assets.payload_path(LEGACY_ID)).read_bytes() == payload
        assert record_dir(ws.assets, LEGACY_ID).as_posix().endswith(f"assets/{LEGACY_ID}")

    def test_find_slug_checks_every_record(self, tmp_path: Path) -> None:
        from tests.support.legacy_assets import LEGACY_ID, write_legacy_data_asset

        ws = Workspace(tmp_path / "lab", name="lab")
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        first = ws.data_assets.import_asset("0-first", source)
        write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=b"legacy\n",
            source_path="/data/legacy.bin",
        )
        names = sorted(path.name for path in (Path(ws.root) / "assets").iterdir())
        assert names[0] == "0-first"
        with pytest.raises(UnmigratedAssetError) as exc_info:
            ws.assets.get(first.id)
        assert exc_info.value.reason == "data-import record"

    def test_persisted_project_id_blocks_list(self, project: Project, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"hi", name="a.bin")
        asset, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        path = record_dir(project.assets, asset.id) / "asset.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["project_id"] = project.id
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(UnmigratedAssetError) as exc_info:
            project.assets.list()
        assert exc_info.value.reason == "persisted project_id"

    def test_pre_origin_version_blocks_versions(self, project: Project, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"hi", name="a.bin")
        asset, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        path = next(record_dir(project.assets, asset.id).glob("versions/*.json"))
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("origin", None)
        raw["source_artifact_id"] = artifact.id
        raw["path"] = "projects/p/assets/model/payload"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(UnmigratedAssetError) as exc_info:
            project.assets.versions(asset.id)
        assert exc_info.value.reason == "pre-origin version"

    def test_null_ref_blocks_versions_and_payload_path(self, project: Project, run: Run) -> None:
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"hi", name="a.bin")
        asset, _version = project.assets.promote(
            artifact, created_by=AgentRef(id="t", type="system")
        )
        path = next(record_dir(project.assets, asset.id).glob("versions/*.json"))
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["origin"]["ref"] = None
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(UnmigratedAssetError) as versions:
            project.assets.versions(asset.id)
        assert versions.value.reason == "unqualified artifact origin"
        with pytest.raises(UnmigratedAssetError) as payload:
            project.assets.payload_path(asset.id)
        assert payload.value.reason == "unqualified artifact origin"

    def test_unknown_id_in_a_clean_scope_is_key_error(self, workspace: Workspace) -> None:
        with pytest.raises(KeyError):
            workspace.assets.get("missing")

    def test_schema_version_alone_is_not_legacy(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        asset = ws.data_assets.import_asset("greeting", source)
        path = record_dir(ws.assets, asset.id) / "asset.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["schema_version"] = 1
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert ws.assets.get(asset.id).id == asset.id
