"""Unit tests for ``molab.workspace.domain`` record shapes.

arch-own-02a-record: ``SourceFile`` / ``SourceManifest`` are frozen,
``extra="forbid"`` value types; ``Execution`` gains ``bypass_cache`` /
``source`` / ``workflow_digest`` with defaults so legacy records still
validate. New symbols are imported inside each test so every test fails for
its own reason before the implementation lands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from molab.workspace.domain import Execution

_DIGEST = "sha256:" + "a" * 64


def _legacy_execution_dict() -> dict[str, Any]:
    return {
        "id": "e01",
        "seq": 1,
        "run_id": "r",
        "project_id": "p",
        "mode": "initial",
        "created_at": "2026-01-01T00:00:00Z",
        "created_by": {"id": "t", "type": "system"},
    }


class TestSourceFile:
    def test_is_frozen(self) -> None:
        from molab.workspace.domain import SourceFile

        entry = SourceFile(name="wf.py", sha256=_DIGEST)
        with pytest.raises(ValidationError):
            entry.name = "other.py"  # type: ignore[misc]

    def test_extra_key_is_rejected(self) -> None:
        from molab.workspace.domain import SourceFile

        with pytest.raises(ValidationError):
            SourceFile.model_validate({"name": "wf.py", "sha256": _DIGEST, "size": 3})


class TestSourceManifest:
    def test_naive_captured_at_is_read_as_utc(self) -> None:
        from molab.workspace.domain import SourceManifest

        manifest = SourceManifest(
            entrypoint="wf.py",
            locator="/abs/wf.py",
            captured_at=datetime(2026, 1, 1),  # naive on purpose
        )
        assert manifest.captured_at.tzinfo is UTC
        assert manifest.captured_at == datetime(2026, 1, 1, tzinfo=UTC)

    def test_dir_key_is_rejected(self) -> None:
        from molab.workspace.domain import SourceManifest

        with pytest.raises(ValidationError):
            SourceManifest.model_validate(
                {
                    "entrypoint": "wf.py",
                    "locator": "/abs/wf.py",
                    "captured_at": "2026-01-01T00:00:00Z",
                    "dir": "source",
                }
            )

    def test_defaults(self) -> None:
        from molab.workspace.domain import SourceManifest

        manifest = SourceManifest(
            entrypoint="wf.py",
            locator="/abs/wf.py",
            captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert manifest.vcs_commit is None
        assert manifest.vcs_dirty is None
        assert manifest.files == ()


class TestExecution:
    def test_legacy_record_validates_with_defaults(self) -> None:
        ex = Execution.model_validate(_legacy_execution_dict())
        assert ex.bypass_cache is False
        assert ex.source is None
        assert ex.workflow_digest is None

    def test_source_round_trips_through_json(self) -> None:
        data = _legacy_execution_dict()
        data["source"] = {
            "entrypoint": "wf.py",
            "locator": "/abs/wf.py",
            "files": [{"name": "wf.py", "sha256": _DIGEST}],
            "vcs_commit": "abc123",
            "vcs_dirty": False,
            "captured_at": "2026-01-01T00:00:00Z",
        }
        data["bypass_cache"] = True
        data["workflow_digest"] = "sha256:d"
        ex = Execution.model_validate(data)
        again = Execution.model_validate(ex.model_dump(mode="json"))
        assert again == ex
        assert again.source is not None
        assert again.source.files[0].name == "wf.py"

    def test_unknown_key_fresh_is_still_rejected(self) -> None:
        data = _legacy_execution_dict()
        data["fresh"] = True
        with pytest.raises(ValidationError):
            Execution.model_validate(data)


def _agent() -> Any:
    from molab.workspace.history import AgentRef

    return AgentRef(id="t", type="system")


def _when() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


class TestAssetScope:
    def test_project_id_follows_kind(self) -> None:
        from molab.workspace.domain import AssetScope

        assert AssetScope(kind="experiment", ids=("p1", "e1")).project_id == "p1"
        assert AssetScope(kind="workspace").project_id is None


class TestAsset:
    def test_dump_omits_scope(self) -> None:
        from molab.workspace.domain import Asset, AssetScope

        asset = Asset(
            id="a",
            scope=AssetScope(kind="project", ids=("p1",)),
            title="t",
            created_at=_when(),
            created_by=_agent(),
        )
        assert "scope" not in asset.model_dump()

    def test_project_id_follows_scope(self) -> None:
        from molab.workspace.domain import Asset, AssetScope

        project = Asset(
            id="a",
            scope=AssetScope(kind="project", ids=("p1",)),
            title="t",
            created_at=_when(),
            created_by=_agent(),
        )
        workspace = project.model_copy(update={"scope": AssetScope(kind="workspace")})
        assert project.project_id == "p1"
        assert workspace.project_id is None

    def test_kind_is_asset_and_not_serialized(self) -> None:
        from molab.workspace.domain import Asset, AssetScope

        asset = Asset(
            id="a",
            scope=AssetScope(kind="project", ids=("p1",)),
            title="t",
            created_at=_when(),
            created_by=_agent(),
        )
        assert asset.kind == "asset"
        assert "kind" not in asset.model_dump()

    def test_persisted_project_id_is_rejected(self) -> None:
        # arch-own-05f ac-001 restates 05c's coerce-on-read: extra=forbid.
        from molab.workspace.domain import Asset, AssetScope

        with pytest.raises(ValidationError):
            Asset.model_validate(
                {
                    "id": "a",
                    "scope": AssetScope(kind="project", ids=("p1",)),
                    "title": "t",
                    "created_at": "2026-01-01T00:00:00Z",
                    "created_by": {"id": "t", "type": "system"},
                    "project_id": "p1",
                }
            )


class TestAssetVersion:
    def test_import_source_artifact_id_is_none_and_content_may_be_absent(self) -> None:
        from molab.workspace.domain import AssetVersion, ImportOrigin

        version = AssetVersion(
            id="v",
            asset_id="a",
            origin=ImportOrigin(uri="/data/qm9", action="copy"),
            content=None,
            version=1,
            created_at=_when(),
            created_by=_agent(),
        )
        assert version.source_artifact_id is None
        assert version.content is None
        assert "path" not in version.model_dump()

    def test_source_artifact_id_projects_artifact_origin(self) -> None:
        from molab.workspace.domain import ArtifactOrigin, AssetVersion

        version = AssetVersion(
            id="v",
            asset_id="a",
            origin=ArtifactOrigin(
                artifact_id="a1",
                ref="molab:experiment/e/run/r/artifact/a1",
            ),
            version=1,
            created_at=_when(),
            created_by=_agent(),
        )
        assert version.source_artifact_id == "a1"

    def test_rejects_pre_origin_shape(self) -> None:
        from molab.workspace.domain import AssetVersion

        with pytest.raises(ValidationError):
            AssetVersion.model_validate(
                {
                    "id": "v",
                    "asset_id": "a",
                    "source_artifact_id": "a1",
                    "path": "projects/x/assets/m/payload",
                    "version": 1,
                    "created_at": "2026-01-01T00:00:00Z",
                    "created_by": {"id": "t", "type": "system"},
                }
            )


class TestArtifactOrigin:
    def test_accepts_matching_ref(self) -> None:
        from molab.workspace.domain import ArtifactOrigin

        origin = ArtifactOrigin(
            artifact_id="a1",
            ref="molab:experiment/e/run/r/artifact/a1",
        )
        assert origin.ref.endswith("/artifact/a1")

    def test_rejects_a_different_artifact_id(self) -> None:
        from molab.workspace.domain import ArtifactOrigin

        with pytest.raises(ValidationError):
            ArtifactOrigin(artifact_id="a2", ref="molab:experiment/e/run/r/artifact/a1")

    def test_rejects_a_run_only_ref(self) -> None:
        from molab.workspace.domain import ArtifactOrigin

        with pytest.raises(ValidationError):
            ArtifactOrigin(artifact_id="a1", ref="molab:experiment/e/run/r")

    def test_ref_is_required(self) -> None:
        # arch-own-05f ac-001: ref=None is no longer a read path.
        from molab.workspace.domain import ArtifactOrigin

        with pytest.raises(ValidationError):
            ArtifactOrigin(artifact_id="a1")  # type: ignore[call-arg]

    def test_accepts_a_molab_ref(self) -> None:
        from molab.workspace.domain import ArtifactOrigin
        from molab.workspace.refs import MolabRef

        origin = ArtifactOrigin(
            artifact_id="a1",
            ref=str(MolabRef(experiment_id="e", run_id="r", artifact_id="a1")),
        )
        assert origin.artifact_id == "a1"


class TestImportOrigin:
    def test_union_round_trip(self) -> None:
        from pydantic import TypeAdapter

        from molab.workspace.domain import AssetOrigin, ImportOrigin

        origin = ImportOrigin(uri="/data/qm9", action="copy", location="assets/qm9/payload")
        again = TypeAdapter(AssetOrigin).validate_python(origin.model_dump())
        assert again == origin

    def test_unknown_action_rejected(self) -> None:
        from molab.workspace.domain import ImportOrigin

        with pytest.raises(ValidationError):
            ImportOrigin(uri="/data/qm9", action="ftp")  # type: ignore[arg-type]


class TestAssetRefRemoved:
    def test_symbol_and_property_are_gone(self) -> None:
        import molab.workspace.domain as domain
        from molab.workspace.domain import Asset

        gone = "Asset" + "Ref"
        assert not hasattr(domain, gone)
        assert gone not in domain.__all__
        assert not hasattr(Asset, "ref")
