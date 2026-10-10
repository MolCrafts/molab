"""ExperimentResponse / RunResponse readers (arch-own-04d)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from molab.server.schemas.responses import ExperimentResponse, ProjectResponse, RunResponse
from molab.workspace import Workspace
from molab.workspace.domain import SourceManifest
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.history import SYSTEM_AGENT

IR = {
    "name": "demo",
    "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
    "links": [],
}
IR_JSON = (
    '{"links": [], "name": "demo", "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}]}'
)


def _ws(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "ws", name="ws")
    ws.materialize()
    return ws


def _source(commit: str) -> SourceManifest:
    return SourceManifest(
        entrypoint="train.py",
        locator="/abs/train.py",
        vcs_commit=commit,
        vcs_dirty=False,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _repo(ws: Workspace, run) -> ExecutionRepository:
    project = run.experiment.project
    return ExecutionRepository(ws.root, run.run_dir, run_id=run.id, project_id=project.id, fs=ws.fs)


class TestProjectResponse:
    def test_ref(self, tmp_path: Path) -> None:
        project = _ws(tmp_path).add_project("p")
        assert ProjectResponse.from_model(project).ref == f"molab:project/{project.id}"


class TestExperimentResponse:
    def test_document_serializes_kind_and_workflow(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        exp.bind_workflow("document", document=IR)
        body = ExperimentResponse.from_model(exp)
        assert body.workflowKind == "document"
        assert body.workflow == IR_JSON
        assert "workflowType" not in ExperimentResponse.model_fields

    def test_unbound_workflow_is_none(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        body = ExperimentResponse.from_model(exp)
        assert body.workflowKind is None
        assert body.workflow is None

    def test_ref(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        assert ExperimentResponse.from_model(exp).ref == f"molab:experiment/{exp.id}"

    def test_workflow_entrypoint(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        code = ws.add_project("p").add_experiment("code")
        loc = "/lab/workflow.py:build"
        code.bind_workflow("code", entrypoint=loc)
        document = ws.get_project("p").add_experiment("doc")
        document.bind_workflow("document", document=IR)
        unbound = ws.get_project("p").add_experiment("free")

        assert ExperimentResponse.from_model(code).workflowEntrypoint == loc
        assert ExperimentResponse.from_model(document).workflowEntrypoint is None
        assert ExperimentResponse.from_model(unbound).workflowEntrypoint is None

    def test_git_commit_is_none_without_runs(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        assert ExperimentResponse.from_model(exp).gitCommit is None

    def test_git_commit_is_the_newer_execution(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        exp = ws.add_project("p").add_experiment("e")
        older = exp.add_run(params={"seed": 1})
        _repo(ws, older).create(created_by=SYSTEM_AGENT, source=_source("1111111"))
        time.sleep(0.05)
        newer = exp.add_run(params={"seed": 2})
        _repo(ws, newer).create(created_by=SYSTEM_AGENT, source=_source("0123abc"))
        body = ExperimentResponse.from_model(exp, runs=[older, newer])
        assert body.gitCommit == "0123abc"


class TestRunResponse:
    def test_ref_is_the_run_reference(self, tmp_path: Path) -> None:
        from molab.workspace.refs import ref_of

        run = _ws(tmp_path).add_project("p").add_experiment("e").add_run(params={"seed": 1})

        assert RunResponse.from_model(run).ref == str(ref_of(run))

    def test_document_without_execution(self, tmp_path: Path) -> None:
        exp = _ws(tmp_path).add_project("p").add_experiment("e")
        exp.bind_workflow("document", document=IR)
        body = RunResponse.from_model(exp.add_run(params={"seed": 1}))
        assert body.workflow is not None
        assert body.workflow.source == "workflow.ir.json"
        assert body.workflow.gitCommit is None
        assert body.workflow.codeHash is None
        assert body.workflow.configHash is None
        assert body.workflowSource == IR_JSON

    def test_latest_execution_fields(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        exp = ws.add_project("p").add_experiment("e")
        exp.bind_workflow("code", entrypoint="train.py:build")
        run = exp.add_run(params={"seed": 1})
        repo = _repo(ws, run)
        created = repo.create(created_by=SYSTEM_AGENT, source=_source("0123abc"))
        repo.start(created.id, environment={"config_hash": "cfg42"}, workflow_digest="sha256:feed")
        body = RunResponse.from_model(run)
        assert body.workflow is not None
        assert body.workflow.gitCommit == "0123abc"
        assert body.workflow.codeHash == "sha256:feed"
        assert body.workflow.configHash == "cfg42"
        assert body.workflow.source == "train.py:build"

    def test_unbound_workflow_is_none(self, tmp_path: Path) -> None:
        run = _ws(tmp_path).add_project("p").add_experiment("e").add_run(params={"seed": 1})
        assert RunResponse.from_model(run).workflow is None

    def test_missing_source_has_no_git_commit(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        exp = ws.add_project("p").add_experiment("e")
        exp.bind_workflow("document", document=IR)
        run = exp.add_run(params={"seed": 1})
        _repo(ws, run).create(created_by=SYSTEM_AGENT, source=None)
        body = RunResponse.from_model(run)
        assert body.workflow is not None
        assert body.workflow.gitCommit is None

    def test_snapshot_git_commit_is_not_read(self, tmp_path: Path) -> None:
        ws = _ws(tmp_path)
        exp = ws.add_project("p").add_experiment("e")
        exp.bind_workflow("document", document=IR)
        run = exp.add_run(params={"seed": 1})
        path = Path(run.run_dir) / "run.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["workflow_snapshot"] = {"git_commit": "zzz"}
        path.write_text(json.dumps(payload), encoding="utf-8")
        fresh = Workspace(ws.root)
        reloaded = fresh.get_project("p").get_experiment("e").get_run(run.id)
        assert "zzz" not in RunResponse.from_model(reloaded).model_dump_json()


def _agent():
    return SYSTEM_AGENT


class TestManagedAssetResponse:
    def test_project_id_comes_from_scope(self) -> None:
        from molab.server.schemas.responses import ManagedAssetResponse
        from molab.workspace.domain import Asset, AssetScope

        asset = Asset(
            id="a",
            scope=AssetScope(kind="project", ids=("p1",)),
            title="t",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=_agent(),
        )
        body = ManagedAssetResponse.from_model(asset, 2)
        assert body.projectId == "p1"
        assert body.versionCount == 2
        assert body.ref == "molab:asset/a"


class TestAssetVersionResponse:
    def test_artifact_origin(self) -> None:
        from molab.server.schemas.responses import AssetVersionResponse
        from molab.workspace.domain import ArtifactOrigin, AssetVersion, ContentRef

        version = AssetVersion(
            id="v",
            asset_id="a",
            origin=ArtifactOrigin(
                artifact_id="art",
                ref="molab:experiment/e/run/r/artifact/art",
            ),
            content=ContentRef(digest="sha256:abc", size=6, kind="file"),
            version=1,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=_agent(),
        )
        body = AssetVersionResponse.from_model(version)
        assert body.originKind == "artifact"
        assert body.originRef == "molab:experiment/e/run/r/artifact/art"
        assert body.sourceArtifactId == "art"

    def test_import_origin_and_missing_content(self) -> None:
        from molab.server.schemas.responses import AssetVersionResponse
        from molab.workspace.domain import AssetVersion, ImportOrigin

        version = AssetVersion(
            id="v",
            asset_id="a",
            origin=ImportOrigin(uri="/data/qm9", action="copy"),
            content=None,
            version=1,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=_agent(),
        )
        body = AssetVersionResponse.from_model(version)
        assert body.originKind == "import"
        assert body.importAction == "copy"
        assert body.sourceArtifactId is None
        assert body.digest is None
