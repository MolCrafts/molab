"""Unit tests for ``molab.workspace.run`` (``Run``).

Logical Run identity and its physical Execution factory.

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the materialize ordering: mkdir -> save the entity JSON ->
record history, so the ``RunDefined`` commit stages an existing ``run.json``
rather than an empty directory. History stays a soft dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.profile import ProfileConfig
from molab.workspace import Run, Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus
from molab.workspace.history import GitHistory

_START_TIME_KEYS = ("host", "pid", "python", "platform")
_PROFILE_KEYS = {"profile", "config", "config_hash"}


def _spy_history(monkeypatch: pytest.MonkeyPatch, entity_file: str) -> list[tuple[str, bool]]:
    """Replace ``GitHistory.record``; log (event, entity JSON exists in paths[0])."""
    seen: list[tuple[str, bool]] = []
    original = GitHistory.record

    def spy(self: GitHistory, event: str, **kwargs: object) -> str | None:
        paths = kwargs.get("paths") or ()
        assert isinstance(paths, tuple)
        exists = bool(paths) and (Path(str(paths[0])) / entity_file).exists()
        seen.append((event, exists))
        return original(self, event, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(GitHistory, "record", spy)
    return seen


class TestRunMaterialize:
    def test_entity_json_exists_when_history_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = Workspace(tmp_path, name="lab")
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        seen = _spy_history(monkeypatch, "run.json")

        experiment.add_run(params={"seed": 1})

        recorded = [exists for event, exists in seen if event == "RunDefined"]
        assert recorded == [True]


class TestRunCreateExecution:
    """arch-own-02a §4: the one public creation entry records creation-time facts."""

    def test_default_records_profile_keys_only(self, run: Run) -> None:
        rec = run.create_execution()

        assert rec.id == "e01"
        assert rec.status is ExecutionStatus.QUEUED
        assert rec.environment == {"profile": None, "config": {}, "config_hash": None}
        assert set(rec.environment) == _PROFILE_KEYS
        assert not set(_START_TIME_KEYS) & set(rec.environment)
        assert rec.executor == {}

    def test_profile_config_and_caller_environment_merge(self, run: Run) -> None:
        rec = run.create_execution(
            profile_config=ProfileConfig({"a": 1}, name="cpu"),
            environment={"script": "s.py"},
        )

        assert rec.environment["profile"] == "cpu"
        assert rec.environment["config_hash"] == ProfileConfig({"a": 1}, name="cpu").content_hash()
        assert rec.environment["script"] == "s.py"

    def test_caller_profile_key_is_rejected(self, run: Run) -> None:
        with pytest.raises(ValueError):
            run.create_execution(environment={"config_hash": "x"})
        assert run.executions == []

    @pytest.mark.parametrize("key", _START_TIME_KEYS)
    def test_start_time_key_in_environment_is_rejected(self, run: Run, key: str) -> None:
        with pytest.raises(ValueError, match="start-time"):
            run.create_execution(environment={key: 1})
        assert run.executions == []

    @pytest.mark.parametrize("key", _START_TIME_KEYS)
    def test_start_time_key_in_executor_is_rejected(self, run: Run, key: str) -> None:
        with pytest.raises(ValueError, match="start-time"):
            run.create_execution(executor={key: 1})
        assert run.executions == []

    def test_non_start_time_executor_keys_are_accepted(self, run: Run) -> None:
        rec = run.create_execution(executor={"backend": "molq", "target": None})

        assert rec.executor == {"backend": "molq", "target": None}

    def test_bypass_cache_is_recorded(self, run: Run) -> None:
        rec = run.create_execution(bypass_cache=True)

        assert rec.bypass_cache is True
        assert run.execution("e01").bypass_cache is True

    def test_initial_after_existing_attempt_is_rejected(self, run: Run) -> None:
        run.create_execution()

        with pytest.raises(ValueError):
            run.create_execution()
        rerun = run.create_execution(mode=ExecutionMode.RERUN)

        assert rerun.id == "e02"


class TestRunExecution:
    """arch-own-02a §4: ``Run.execution(id)`` is the public single-record read."""

    def test_returns_the_recorded_attempt(self, run: Run) -> None:
        with run.start():
            pass

        assert run.execution("e01") == run.executions[0]

    def test_unknown_id_raises_key_error(self, run: Run) -> None:
        with pytest.raises(KeyError):
            run.execution("e99")


class TestRunStart:
    """arch-own-02a §4: ``Run.start(bypass_cache=)`` reaches the record."""

    def test_bypass_cache_is_forwarded(self, run: Run) -> None:
        with run.start(bypass_cache=True):
            pass

        assert run.executions[-1].bypass_cache is True

    def test_bypass_cache_defaults_false(self, run: Run) -> None:
        with run.start():
            pass

        assert run.executions[-1].bypass_cache is False
