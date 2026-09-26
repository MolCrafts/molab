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

from molab.ids import compute_content_hash
from molab.profile import ProfileConfig
from molab.workspace import Run, Workspace
from molab.workspace.domain import ExecutionMode, ExecutionStatus, SourceFile, SourceManifest
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


def _source_tree(factory: pytest.TempPathFactory) -> Path:
    """``entry.py`` + first-party ``helper.py``, outside the workspace tree."""
    src = factory.mktemp("src")
    (src / "entry.py").write_text("import helper\nimport json\n", encoding="utf-8")
    (src / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    return src / "entry.py"


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

    # --- arch-own-02b §3: source capture per execution ----------------------

    def test_source_entrypoint_records_manifest_and_copies_per_execution(
        self, run: Run, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        entry = _source_tree(tmp_path_factory)

        rec = run.create_execution(source_entrypoint=entry)

        assert rec.id == "e01"
        assert rec.status is ExecutionStatus.QUEUED
        assert rec.source is not None
        assert rec.source.entrypoint == "entry.py"
        copied = run.run_dir / "executions" / "e01" / "source" / "entry.py"
        assert copied.is_file()
        assert rec.source.files[0].sha256 == compute_content_hash(copied)
        assert not (run.run_dir / "source").exists()

    def test_without_source_entrypoint_nothing_is_captured(self, run: Run) -> None:
        rec = run.create_execution()

        assert rec.source is None
        assert not (run.run_dir / "executions" / "e01" / "source").exists()

    def test_failed_capture_seals_the_attempt_failed(
        self,
        run: Run,
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from molab.workspace.source_snapshot import SourceCaptureError, source_manifest

        entry = _source_tree(tmp_path_factory)
        real = source_manifest(entry)
        forged = real.model_copy(
            update={
                "files": (
                    SourceFile(name="entry.py", sha256="sha256:" + "0" * 64),
                    *real.files[1:],
                )
            }
        )

        def forged_manifest(*_args: object, **_kwargs: object) -> SourceManifest:
            return forged

        monkeypatch.setattr("molab.workspace.run.source_manifest", forged_manifest)

        with pytest.raises(SourceCaptureError):
            run.create_execution(source_entrypoint=entry)

        last = run.executions[-1]
        assert last.status is ExecutionStatus.FAILED
        assert last.error is not None
        assert last.error["type"] == "SourceCaptureError"
        assert last.sealed is True

    def test_missing_entrypoint_creates_no_record(
        self, run: Run, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        missing = tmp_path_factory.mktemp("nosrc") / "entry.py"

        with pytest.raises(FileNotFoundError):
            run.create_execution(source_entrypoint=missing)

        assert run.executions == []

    def test_interrupted_capture_seals_the_attempt_failed(
        self,
        run: Run,
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entry = _source_tree(tmp_path_factory)

        def interrupted(*_args: object, **_kwargs: object) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr("molab.workspace.run.copy_sources", interrupted)

        with pytest.raises(KeyboardInterrupt):
            run.create_execution(source_entrypoint=entry)

        last = run.executions[-1]
        assert last.status is ExecutionStatus.FAILED
        assert last.sealed is True
        assert last.error is not None
        assert last.error["type"] == "SourceCaptureError"


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
