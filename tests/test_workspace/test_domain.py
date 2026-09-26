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
