"""Case bodies for the arch-own-05e writer tests.

Collected only through the ``Test*`` subclasses in ``test_artifact_repository.py``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from molab.workspace import Workspace
from molab.workspace.artifact_repository import (
    AssetRepository,
    content_ref,
    migrate_legacy_assets,
)
from molab.workspace.domain import Asset
from molab.workspace.errors import UnmigratedAssetError
from molab.workspace.fs_local import LocalFileSystem
from molab.workspace.history import SYSTEM_AGENT, GitHistory
from molab.workspace.refs import MolabRef
from molab.workspace.schema_version import MOLAB_SCHEMA_VERSION
from tests.support.legacy_assets import (
    DIGEST,
    HELLO,
    LEGACY_ID,
    write_legacy_data_asset,
    write_legacy_domain_asset,
)


def record_dir(repo: AssetRepository, asset_id: str) -> Path:
    """The record directory ``promote`` writes, addressed by the private slug."""
    return Path(repo.fs.join(repo.assets_dir, repo._slug_of(asset_id)))


B_ID = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6c"
C_ID = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6d"
MISSING_ART = "0190ffff-0000-7000-8000-000000000000"


class _NonLocal:
    """A filesystem that delegates every call and is not a LocalFileSystem."""

    def __init__(self, inner: LocalFileSystem) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def _ws(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "ws", name="lab")


def _src(tmp_path: Path, name: str = "hello.txt", data: bytes = HELLO) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _asset_dirs(root: Path) -> set[str]:
    assets = root / "assets"
    if not assets.is_dir():
        return set()
    return {path.name for path in assets.iterdir() if path.is_dir()}


def _snapshot(root: Path) -> tuple[set[str], dict[str, str]]:
    paths: set[str] = set()
    files: dict[str, str] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        paths.add(rel)
        if path.is_file() and not path.is_symlink():
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return paths, files


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


class ImportAssetCases:
    def test_copy_writes_the_unified_record(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path)
        asset = ws.assets.import_asset("greeting", src, action="copy")
        assert type(asset) is Asset
        assert asset.id[14] == "7"
        assert asset.title == "greeting"
        assert asset.scope.kind == "workspace"
        versions = ws.assets.versions(asset.id)
        assert len(versions) == 1
        version = versions[0]
        assert version.version == 1
        assert version.origin.kind == "import"
        assert version.origin.action == "copy"
        assert version.origin.location == "assets/greeting/payload"
        assert version.origin.uri == str(src.resolve())
        assert version.origin.input_ids == ()
        assert version.content is not None
        assert version.content.digest == DIGEST
        assert version.content.size == 6
        assert version.content.kind == "file"
        record = record_dir(ws.assets, asset.id)
        raw = json.loads((record / "asset.json").read_text(encoding="utf-8"))
        assert raw["schema_version"] == MOLAB_SCHEMA_VERSION
        assert "scope" not in raw
        assert "project_id" not in raw
        stored = json.loads((record / "versions" / "v001.json").read_text(encoding="utf-8"))
        assert "path" not in stored
        assert "source_artifact_id" not in stored
        assert Path(ws.assets.payload_path(asset.id)).read_bytes() == HELLO
        assert src.is_file()

    def test_move_consumes_the_source(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path)
        asset = ws.assets.import_asset("greeting", src, action="move")
        assert not src.exists()
        assert Path(ws.assets.payload_path(asset.id)).read_bytes() == HELLO

    def test_symlink_and_hardlink_store_no_content(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        link_src = _src(tmp_path, "link.txt")
        linked = ws.assets.import_asset("linked", link_src, action="symlink")
        link_version = ws.assets.versions(linked.id)[0]
        payload = Path(ws.assets.payload_path(linked.id))
        assert payload.is_symlink()
        assert link_version.content is None
        hard_src = _src(tmp_path, "hard.txt")
        hard = ws.assets.import_asset("hard", hard_src, action="hardlink")
        hard_version = ws.assets.versions(hard.id)[0]
        hard_payload = Path(ws.assets.payload_path(hard.id))
        assert hard_version.content is None
        if hard_payload.stat().st_ino != hard_src.stat().st_ino:
            assert hard_payload.read_bytes() == hard_src.read_bytes()

    def test_reference_points_at_the_source(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path)
        asset = ws.assets.import_asset("greeting", src, action="reference")
        version = ws.assets.versions(asset.id)[0]
        assert version.origin.location is None
        assert ws.assets.payload_path(asset.id) == str(src.resolve())
        assert version.content is not None
        assert version.content.digest.startswith("sha256:")
        record = record_dir(ws.assets, asset.id)
        assert not (record / "payload").exists()
        assert not any(path.is_symlink() for path in Path(ws.root).rglob("*"))

    def test_reference_directory_reads_its_child(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        folder = tmp_path / "ckpt"
        folder.mkdir()
        (folder / "last.pt").write_bytes(b"ckpt")
        asset = ws.assets.import_asset("weights", folder, action="reference")
        payload = Path(ws.assets.payload_path(asset.id))
        assert (payload / "last.pt").read_bytes() == b"ckpt"

    def test_directory_copy_is_a_directory_content(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        folder = tmp_path / "tree"
        folder.mkdir()
        (folder / "a.txt").write_bytes(HELLO)
        asset = ws.assets.import_asset("tree", folder, action="copy")
        version = ws.assets.versions(asset.id)[0]
        assert version.content is not None
        assert version.content.kind == "directory"
        assert version.content == content_ref(ws.fs, ws.assets.payload_path(asset.id))

    def test_consumed_and_meta_land_on_the_record(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset(
            "greeting", _src(tmp_path), consumed=["a", "b"], meta={"stage": "raw"}
        )
        version = ws.assets.versions(asset.id)[0]
        assert version.origin.input_ids == ("a", "b")
        assert asset.tags == {"stage": "raw"}

    def test_a_repeated_name_gets_a_suffix(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        src = _src(tmp_path)
        first = ws.assets.import_asset("greeting", src)
        second = ws.assets.import_asset("greeting", src)
        names = {
            record_dir(ws.assets, first.id).name,
            record_dir(ws.assets, second.id).name,
        }
        assert names == {"greeting", "greeting-2"}
        assert first.id != second.id

    def test_missing_source_leaves_no_directory(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        with pytest.raises(FileNotFoundError):
            ws.assets.import_asset("ghost", tmp_path / "nope.bin", action="reference")
        assert _asset_dirs(Path(ws.root)) == set()

    def test_unknown_action_leaves_no_directory(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        with pytest.raises(ValueError):
            ws.assets.import_asset("greeting", _src(tmp_path), action="teleport")  # type: ignore[arg-type]
        assert _asset_dirs(Path(ws.root)) == set()

    def test_materialize_failure_leaves_no_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = _ws(tmp_path)

        def boom(src: Path, dest: Path, action: str) -> None:
            raise OSError("full")

        monkeypatch.setattr(AssetRepository, "_materialize", staticmethod(boom))
        with pytest.raises(OSError):
            ws.assets.import_asset("greeting", _src(tmp_path))
        assert _asset_dirs(Path(ws.root)) == set()

    def test_experiment_scope_is_relative_to_the_experiment(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        experiment = ws.add_project("p").add_experiment("e")
        asset = experiment.assets.import_asset("greeting", _src(tmp_path))
        version = experiment.assets.versions(asset.id)[0]
        assert version.origin.location == "assets/greeting/payload"
        payload = Path(experiment.experiment_dir) / "assets" / "greeting" / "payload"
        assert payload.read_bytes() == HELLO

    def test_non_local_filesystem_raises_before_write(self, tmp_path: Path) -> None:
        root = tmp_path / "ws"
        root.mkdir()
        ws = Workspace(root, name="lab", fs=_NonLocal(LocalFileSystem()))
        with pytest.raises(NotImplementedError):
            ws.assets.import_asset("greeting", _src(tmp_path))
        assert not (root / "assets").exists()

    def test_import_records_asset_version_created(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        ws.materialize()
        GitHistory(ws.root).init()
        ws.assets.import_asset("greeting", _src(tmp_path))
        body = _git(Path(ws.root), "log", "-1", "--format=%B")
        assert "Molab-Event: AssetVersionCreated" in body


class RegisterInPlaceCases:
    def test_records_the_scope_relative_file(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        ws.materialize()
        dataset = Path(ws.root) / "qm9.tar.bz2"
        dataset.write_bytes(b"data")
        (dataset.parent / "qm9.py").write_text("x = 1", encoding="utf-8")
        asset = ws.assets.register_in_place("qm9.tar.bz2", dataset)
        version = ws.assets.versions(asset.id)[0]
        assert version.origin.action == "reference"
        assert version.origin.location == "qm9.tar.bz2"
        assert version.origin.uri == str(dataset.resolve())
        assert Path(ws.assets.payload_path(asset.id)) == dataset.resolve()
        assert (dataset.parent / "qm9.py").is_file()
        assert not (record_dir(ws.assets, asset.id) / "payload").exists()
        assert version.content is not None
        assert version.content.digest.startswith("sha256:")

    def test_outside_source_raises(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"x")
        with pytest.raises(ValueError):
            ws.assets.register_in_place("outside.bin", outside)

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        with pytest.raises(FileNotFoundError):
            ws.assets.register_in_place("ghost", tmp_path / "ghost.bin")


class RewriteLegacyCases:
    def test_data_asset_copy_matches_the_golden(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        directory = write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
            inputs=("up-1",),
        )
        payload = directory / "payload"
        inode = payload.stat().st_ino
        report = ws.assets.rewrite_legacy()
        assert tuple(Path(path).resolve() for path in report.rewritten) == (directory.resolve(),)
        assert report.unresolved == ()
        raw = json.loads((directory / "asset.json").read_text(encoding="utf-8"))
        assert raw == {
            "schema_version": MOLAB_SCHEMA_VERSION,
            "id": LEGACY_ID,
            "title": "legacy-data",
            "created_at": "2026-01-02T03:04:05Z",
            "created_by": SYSTEM_AGENT.model_dump(mode="json"),
            "tags": {},
        }
        stored = json.loads((directory / "versions" / "v001.json").read_text(encoding="utf-8"))
        assert stored["id"] == f"{LEGACY_ID}-v001"
        assert stored["origin"] == {
            "kind": "import",
            "uri": "/data/hello.bin",
            "action": "copy",
            "location": f"assets/{LEGACY_ID}/payload",
            "input_ids": ["up-1"],
        }
        assert stored["content"] == {"digest": DIGEST, "size": 6, "kind": "file"}
        assert "path" not in stored
        assert "source_artifact_id" not in stored
        assert payload.stat().st_ino == inode
        assert payload.read_bytes() == HELLO
        assert payload.parent.name == LEGACY_ID
        assert ws.assets.rewrite_legacy().rewritten == ()

    def test_invalid_import_action_is_not_unresolved(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        directory = write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="teleport",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
        )
        before = (directory / "asset.json").read_bytes()
        with pytest.raises(ValidationError):
            ws.assets.rewrite_legacy()
        assert (directory / "asset.json").read_bytes() == before

    def test_reads_equal_before_and_after(self, tmp_path: Path) -> None:
        """05f raises on a legacy read, so equality is the folded record after rewrite."""
        ws = _ws(tmp_path)
        copy_dir = write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
            inputs=("up-1",),
        )
        with pytest.raises(UnmigratedAssetError):
            ws.assets.get(LEGACY_ID)
        ws.assets.rewrite_legacy()
        assert ws.assets.get(LEGACY_ID).title == "legacy-data"
        assert Path(ws.assets.payload_path(LEGACY_ID)).read_bytes() == HELLO
        assert ws.assets.versions(LEGACY_ID)[0].origin.location == f"assets/{LEGACY_ID}/payload"
        assert copy_dir.name == LEGACY_ID

    def test_domain_record_gains_a_qualified_ref(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            artifact = ctx.emit_artifact(HELLO, name="hello.txt")
        content = artifact.content.model_dump(mode="json")
        directory = write_legacy_domain_asset(
            Path(project.project_dir),
            asset_id=C_ID,
            project_id=project.id,
            title="model",
            artifact_id=artifact.id,
            content=content,
        )
        report = project.assets.rewrite_legacy()
        assert Path(report.rewritten[0]).resolve() == directory.resolve()
        raw = json.loads((directory / "asset.json").read_text(encoding="utf-8"))
        assert "project_id" not in raw
        assert raw["schema_version"] == MOLAB_SCHEMA_VERSION
        stored = json.loads((directory / "versions" / "v001.json").read_text(encoding="utf-8"))
        assert "path" not in stored
        assert "source_artifact_id" not in stored
        assert stored["origin"]["artifact_id"] == artifact.id
        assert stored["origin"]["ref"] == str(
            MolabRef(experiment_id=experiment.id, run_id=run.id, artifact_id=artifact.id)
        )
        assert stored["content"] == content
        assert stored["id"] == f"{C_ID}-v001"

    def test_unresolved_artifact_is_left_untouched(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        directory = write_legacy_domain_asset(
            Path(project.project_dir),
            asset_id=C_ID,
            project_id=project.id,
            title="model",
            artifact_id=MISSING_ART,
            content={"digest": DIGEST, "size": 6, "kind": "file"},
        )
        before = {
            path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*")
            if path.is_file()
        }
        report = project.assets.rewrite_legacy()
        assert report.unresolved == (C_ID,)
        assert report.rewritten == ()
        after = {
            path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*")
            if path.is_file()
        }
        assert after == before

    def test_dry_run_writes_nothing_and_matches_a_real_run(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
            inputs=("up-1",),
        )
        before = _snapshot(Path(ws.root))
        dry = ws.assets.rewrite_legacy(dry_run=True)
        assert _snapshot(Path(ws.root)) == before
        assert not (Path(ws.root) / ".molab" / "locks" / "workspace.assets.lock").exists()
        real = ws.assets.rewrite_legacy()
        assert dry.rewritten == real.rewritten

    def test_schema_version_alone_does_not_rewrite(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        asset = ws.assets.import_asset("greeting", _src(tmp_path))
        record = record_dir(ws.assets, asset.id)
        for name in ("asset.json", "versions/v001.json"):
            path = record / name
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["schema_version"] = 1
            path.write_text(json.dumps(raw), encoding="utf-8")
        before = path.read_bytes()
        assert ws.assets.rewrite_legacy().rewritten == ()
        assert path.read_bytes() == before


class MigrateLegacyCases:
    def _lab(self, tmp_path: Path, *, manifests: int = 5):
        ws = _ws(tmp_path)
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run()
        with run.start() as ctx:
            ctx.emit_artifact(HELLO, name="hello.txt")
        artifact = run.executions[0].artifacts[0]
        write_legacy_data_asset(
            Path(ws.root),
            asset_id=LEGACY_ID,
            name="legacy-data",
            scope_kind="workspace",
            action="copy",
            payload=HELLO,
            source_path="/data/hello.bin",
            content_hash=DIGEST,
            inputs=("up-1",),
        )
        external = tmp_path / "remote.bin"
        external.write_bytes(HELLO)
        write_legacy_data_asset(
            Path(experiment.experiment_dir),
            asset_id=B_ID,
            name="remote",
            scope_kind="experiment",
            scope_ids=(project.id, experiment.id),
            action="reference",
            payload=None,
            source_path="",
            external_uri=str(external.resolve()),
            rel_path=None,
            content_hash=DIGEST,
        )
        write_legacy_domain_asset(
            Path(project.project_dir),
            asset_id=C_ID,
            project_id=project.id,
            title="model",
            artifact_id=artifact.id,
            content=artifact.content.model_dump(mode="json"),
        )
        bodies = {"schema_version": 1, "assets": {}}
        homes = [
            Path(ws.root),
            Path(project.project_dir),
            Path(experiment.experiment_dir),
            Path(run.run_dir),
            Path(run.execution_dir("e01")),
        ]
        for home in homes[:manifests]:
            (home / "assets.json").write_text(json.dumps(bodies), encoding="utf-8")
        user = Path(run.execution_dir("e01")) / "out" / "task" / "assets.json"
        user.parent.mkdir(parents=True, exist_ok=True)
        user.write_text("{}", encoding="utf-8")
        return ws, project, experiment, run, user

    def test_real_run_rewrites_three_and_drops_five_manifests(self, tmp_path: Path) -> None:
        ws, project, experiment, run, user = self._lab(tmp_path)
        execution = Path(run.execution_dir("e01")) / "execution.json"
        before = execution.read_bytes()
        report = migrate_legacy_assets(ws)
        assert len(report.rewritten) == 3
        assert len(report.manifests_removed) == 5
        assert report.unresolved == ()
        assert all(
            not path.startswith("/") for path in (*report.rewritten, *report.manifests_removed)
        )
        assert user.is_file()
        assert ws.assets.get(LEGACY_ID).id == LEGACY_ID
        assert experiment.assets.get(B_ID).id == B_ID
        assert project.assets.versions(C_ID)[0].origin.ref  # type: ignore[union-attr]
        assert execution.read_bytes() == before

    def test_dry_run_matches_counts_and_writes_nothing(self, tmp_path: Path) -> None:
        ws, _project, _experiment, _run, _user = self._lab(tmp_path)
        before = _snapshot(Path(ws.root))
        report = migrate_legacy_assets(ws, dry_run=True)
        assert len(report.rewritten) == 3
        assert len(report.manifests_removed) == 5
        assert report.commit is None
        assert _snapshot(Path(ws.root)) == before

    def test_second_run_is_empty(self, tmp_path: Path) -> None:
        ws, _project, _experiment, _run, _user = self._lab(tmp_path)
        migrate_legacy_assets(ws)
        again = migrate_legacy_assets(ws)
        assert again.rewritten == ()
        assert again.manifests_removed == ()
        assert again.commit is None

    def test_git_commits_the_migration_and_leaves_scratch(self, tmp_path: Path) -> None:
        ws, _project, _experiment, run, user = self._lab(tmp_path, manifests=4)
        root = Path(ws.root)
        history = GitHistory(root)
        history.init()
        assert history.sweep("baseline") is not None
        fifth = Path(run.execution_dir("e01")) / "assets.json"
        fifth.write_text(json.dumps({"schema_version": 1, "assets": {}}), encoding="utf-8")
        (root / "scratch.txt").write_text("leave me", encoding="utf-8")
        before = int(_git(root, "rev-list", "--count", "HEAD"))
        report = migrate_legacy_assets(ws)
        assert int(_git(root, "rev-list", "--count", "HEAD")) == before + 1
        assert "Molab-Event: AssetsMigrated" in _git(root, "log", "-1", "--format=%B")
        assert report.commit == _git(root, "rev-parse", "HEAD").strip()
        assert "scratch.txt" in _git(root, "status", "--porcelain")
        tracked = set(_git(root, "ls-files").splitlines())
        # out/ is gitignored, so the user file stays on disk and was never indexed.
        assert "assets.json" not in tracked
        assert not any(line.endswith("assets.json") for line in tracked)
        assert not fifth.exists()
        assert user.is_file()

    def test_non_local_raises(self, tmp_path: Path) -> None:
        root = tmp_path / "ws"
        root.mkdir()
        ws = Workspace(root, name="lab", fs=_NonLocal(LocalFileSystem()))
        with pytest.raises(NotImplementedError):
            migrate_legacy_assets(ws)
