"""Unit tests for ``molab.workspace.domain`` record shapes.

arch-own-02a-record: ``SourceFile`` / ``SourceManifest`` are frozen,
``extra="forbid"`` value types; ``Execution`` gains ``bypass_cache`` /
``source`` / ``workflow_hash`` with defaults so legacy records still
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
    def test_naive_captured_at_is_read_as_local_time(self) -> None:
        from molab.workspace.domain import SourceManifest

        manifest = SourceManifest(
            entrypoint="wf.py",
            locator="/abs/wf.py",
            captured_at=datetime(2026, 1, 1),  # naive on purpose
        )
        # A naive stamp was written by datetime.now(): local time, converted.
        assert manifest.captured_at.tzinfo is UTC
        assert manifest.captured_at == datetime(2026, 1, 1).astimezone(UTC)

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
        assert ex.workflow_hash is None

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
        data["workflow_hash"] = "sha256:d"
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

    def test_legacy_product_keys_are_dropped(self) -> None:
        data = _legacy_execution_dict()
        data["artifacts"] = [{"id": "old"}]
        data["checkpoint_artifact_id"] = "cp"
        data["observed_input_ids"] = ["in"]
        data["workflow_digest"] = "sha256:abc"
        ex = Execution.model_validate(data)
        dumped = ex.model_dump()
        assert "artifacts" not in dumped
        assert "checkpoint_artifact_id" not in dumped
        assert "observed_input_ids" not in dumped
        assert ex.workflow_hash == "sha256:abc"


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


def _asset(**overrides: Any):
    from molab.workspace.domain import Asset, AssetScope, ContentRef, ExecutionOrigin

    fields: dict[str, Any] = {
        "id": "a",
        "scope": AssetScope(kind="project", ids=("p1",)),
        "title": "t",
        "content": ContentRef(digest="sha256:" + "ab" * 32, size=1),
        "origin": ExecutionOrigin(
            project_id="p1",
            experiment_id="e1",
            run_id="r1",
            execution_id="e01",
        ),
        "file": "payload.bin",
        "created_at": _when(),
        "created_by": _agent(),
    }
    fields.update(overrides)
    return Asset(**fields)


class TestAsset:
    def test_dump_omits_scope(self) -> None:
        asset = _asset()
        assert "scope" not in asset.model_dump()

    def test_project_id_follows_scope(self) -> None:
        from molab.workspace.domain import AssetScope

        project = _asset()
        workspace = project.model_copy(update={"scope": AssetScope(kind="workspace")})
        assert project.project_id == "p1"
        assert workspace.project_id is None

    def test_kind_is_not_a_field(self) -> None:
        asset = _asset()
        assert not hasattr(asset, "kind")
        assert "kind" not in asset.model_dump()

    def test_persisted_project_id_is_rejected(self) -> None:
        from molab.workspace.domain import Asset, AssetScope, ContentRef, ExecutionOrigin

        with pytest.raises(ValidationError):
            Asset.model_validate(
                {
                    "id": "a",
                    "scope": AssetScope(kind="project", ids=("p1",)),
                    "title": "t",
                    "content": ContentRef(digest="sha256:" + "ab" * 32, size=1).model_dump(),
                    "origin": ExecutionOrigin(
                        project_id="p1",
                        experiment_id="e1",
                        run_id="r1",
                        execution_id="e01",
                    ).model_dump(),
                    "file": "payload.bin",
                    "created_at": "2026-01-01T00:00:00Z",
                    "created_by": {"id": "t", "type": "system"},
                    "project_id": "p1",
                }
            )

    def test_ref_is_the_asset_scheme(self) -> None:
        asset = _asset()
        assert asset.ref == "molab:asset/a"
        assert "ref" not in asset.model_dump()


class TestExecutionOrigin:
    def test_round_trip(self) -> None:
        from molab.workspace.domain import ExecutionOrigin

        origin = ExecutionOrigin(
            project_id="p1",
            experiment_id="e1",
            run_id="r1",
            execution_id="e01",
            task="train",
        )
        again = ExecutionOrigin.model_validate(origin.model_dump())
        assert again == origin
        assert again.kind == "execution"
        assert again.task == "train"

    def test_task_defaults_to_none(self) -> None:
        from molab.workspace.domain import ExecutionOrigin

        origin = ExecutionOrigin(
            project_id="p1",
            experiment_id="e1",
            run_id="r1",
            execution_id="e01",
        )
        assert origin.task is None


class TestImportOrigin:
    def test_union_round_trip(self) -> None:
        from pydantic import TypeAdapter

        from molab.workspace.domain import AssetOrigin, ImportOrigin

        origin = ImportOrigin(uri="/data/qm9")
        again = TypeAdapter(AssetOrigin).validate_python(origin.model_dump())
        assert again == origin
        assert again.uri == "/data/qm9"

    def test_unknown_extra_rejected(self) -> None:
        from molab.workspace.domain import ImportOrigin

        with pytest.raises(ValidationError):
            ImportOrigin(uri="/data/qm9", action="copy")  # type: ignore[call-arg]


class TestAssetRefSymbol:
    def test_asset_ref_type_is_absent(self) -> None:
        import molab.workspace.domain as domain

        gone = "Asset" + "Ref"
        assert not hasattr(domain, gone)
        assert gone not in domain.__all__
