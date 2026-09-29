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
_DIGEST = "sha256:" + "ab" * 32


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
        run.cancel("e01")
        rerun = run.create_execution(mode=ExecutionMode.RERUN)

        assert rerun.id == "e02"

    # --- arch-own-03a §1b (D57): creation-time config inheritance -----------

    def test_non_initial_without_profile_inherits_predecessor_config(self, run: Run) -> None:
        cpu = ProfileConfig({"k": 1}, name="cpu")
        with pytest.raises(RuntimeError), run.start(cpu):
            raise RuntimeError("boom")
        e01 = run.execution("e01").environment

        resume = run.create_execution(mode=ExecutionMode.RESUME)

        assert resume.based_on_execution_id == "e01"
        assert resume.environment["profile"] == "cpu"
        assert resume.environment["config"] == {"k": 1}
        assert resume.environment["config_hash"] == e01["config_hash"]
        assert e01["config_hash"] is not None

        run.cancel(resume.id)
        explicit = run.create_execution(
            mode=ExecutionMode.RERUN, profile_config=ProfileConfig({"k": 2}, name=None)
        )
        assert (
            explicit.environment["config_hash"] == ProfileConfig({"k": 2}, name=None).content_hash()
        )
        assert explicit.environment["config_hash"] != e01["config_hash"]

        run.cancel(explicit.id)
        empty = run.create_execution(
            mode=ExecutionMode.RERUN, profile_config=ProfileConfig({}, name=None)
        )
        assert empty.environment["config"] == {}
        assert empty.environment["config_hash"] is None

    @pytest.mark.parametrize("mode", [ExecutionMode.RERUN, ExecutionMode.REPRODUCE])
    def test_inherits_after_success(self, run: Run, mode: ExecutionMode) -> None:
        with run.start(ProfileConfig({"k": 1}, name="cpu")):
            pass
        e01 = run.execution("e01").environment

        rec = run.create_execution(mode=mode)

        assert rec.based_on_execution_id == "e01"
        assert {k: rec.environment[k] for k in _PROFILE_KEYS} == {
            "profile": "cpu",
            "config": {"k": 1},
            "config_hash": e01["config_hash"],
        }

    def test_initial_without_profile_is_empty(self, run: Run) -> None:
        rec = run.create_execution(mode=ExecutionMode.INITIAL)

        assert rec.environment == {"profile": None, "config": {}, "config_hash": None}

    def test_inherited_missing_hash_is_none(self, run: Run) -> None:
        import json

        with pytest.raises(RuntimeError), run.start(ProfileConfig({"k": 1}, name="cpu")):
            raise RuntimeError("boom")
        path = run.execution_dir("e01") / "execution.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["environment"]["config_hash"]
        path.write_text(json.dumps(raw), encoding="utf-8")

        rec = run.create_execution(mode=ExecutionMode.RERUN)

        assert "config_hash" in rec.environment
        assert rec.environment["config_hash"] is None
        assert rec.environment["profile"] == "cpu"

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

    def test_workflow_digest_is_recorded(self, run: Run) -> None:
        with run.start(workflow_digest=_DIGEST):
            pass

        assert run.executions[-1].workflow_digest == _DIGEST

    def test_workflow_digest_defaults_none(self, run: Run) -> None:
        with run.start():
            pass

        assert run.executions[-1].workflow_digest is None

    def test_workflow_digest_with_explicit_id(self, run: Run) -> None:
        rec = run.create_execution()
        assert rec.workflow_digest is None

        with run.start(execution_id=rec.id, workflow_digest=_DIGEST):
            pass

        assert run.execution(rec.id).workflow_digest == _DIGEST
        assert len(run.executions) == 1


class TestRunExecutionDir:
    """arch-own-03a §2: the public, pure execution-directory accessor."""

    def test_is_the_layout_path_and_is_not_created(self, run: Run) -> None:
        path = run.execution_dir("e01")

        assert isinstance(path, Path)
        assert path == Path(run.run_dir) / "executions" / "e01"
        assert not path.exists()

    def test_accepts_a_legacy_uuid_id(self, run: Run) -> None:
        legacy = "0190f3c2-7e1a-7000-8000-000000000000"

        assert run.execution_dir(legacy) == Path(run.run_dir) / "executions" / legacy

    @pytest.mark.parametrize("bad", ["", "../x", "a/b", "..", ".", "a\\b"])
    def test_rejects_path_like_ids(self, run: Run, bad: str) -> None:
        with pytest.raises(ValueError):
            run.execution_dir(bad)


class TestRunMachineDir:
    """arch-own-03a §2: ``<root>/.molab/runs/<run-id>``, never created."""

    def test_is_under_the_workspace_machine_dir(self, workspace: Workspace, run: Run) -> None:
        path = run.machine_dir()

        assert isinstance(path, Path)
        assert path == Path(str(workspace.root)) / ".molab" / "runs" / run.id
        assert not path.exists()

    def test_two_runs_differ(self, run: Run) -> None:
        other = run.experiment.add_run(params={"lr": 2e-4})

        assert run.machine_dir() != other.machine_dir()


def _fail_then_retry(run: Run) -> None:
    """e01 fails, e02 (a RETRY of e01) succeeds — built through the public API."""
    with pytest.raises(RuntimeError), run.start():
        raise RuntimeError("boom")
    with run.start(mode=ExecutionMode.RETRY, based_on_execution_id="e01"):
        pass


class TestRunStatusLabel:
    """arch-own-02e D70: ``status_label`` is the latest attempt; history is ``has_failures``."""

    def test_latest_success_after_failure_reads_succeeded(self, run: Run) -> None:
        _fail_then_retry(run)

        assert run.status_label == "succeeded"
        assert run.has_failures is True
        assert run.is_retryable is True

    def test_no_attempt_reads_pending(self, run: Run) -> None:
        assert run.status_label == "pending"
        assert run.has_failures is False

    def test_single_failed_attempt_reads_failed(self, run: Run) -> None:
        with pytest.raises(RuntimeError), run.start():
            raise RuntimeError("boom")

        assert run.status_label == "failed"
        assert run.has_failures is True

    def test_queued_attempt_reads_queued(self, run: Run) -> None:
        run.create_execution()

        assert run.status_label == "queued"
        assert run.has_failures is False
        assert run.is_retryable is False


class TestRunFinishedAt:
    """arch-own-02e D70: ``finished_at`` belongs to the latest attempt, like ``status_label``."""

    def test_latest_queued_after_failure_is_none(self, run: Run) -> None:
        with pytest.raises(RuntimeError), run.start():
            raise RuntimeError("boom")
        assert run.executions[0].finished_at is not None
        run.create_execution(mode=ExecutionMode.RETRY, based_on_execution_id="e01")

        assert run.status_label == "queued"
        assert run.finished_at is None

    def test_latest_success_after_failure_is_its_finish(self, run: Run) -> None:
        _fail_then_retry(run)
        e02 = run.executions[-1]

        assert e02.id == "e02"
        assert e02.finished_at is not None
        assert run.finished_at == e02.finished_at

    def test_no_attempt_is_none(self, run: Run) -> None:
        assert run.finished_at is None


def _results_file(run: Run, execution_id: str) -> Path:
    return Path(str(run.execution_dir(execution_id))) / "results.json"


class TestRunResults:
    def test_returns_driver_results(self, run: Run) -> None:
        with run.start() as ctx:
            ctx.set_result("a", 1)
            ctx.set_result("b", [1, 2])
            eid = ctx.id
        assert run.results(eid) == {"a": 1, "b": [1, 2]}

    def test_empty_without_results_file(self, run: Run) -> None:
        with run.start() as ctx:
            eid = ctx.id
        assert run.results(eid) == {}

    def test_empty_results_file_is_empty(self, run: Run) -> None:
        with run.start() as ctx:
            eid = ctx.id
        _results_file(run, eid).write_text("")
        assert run.results(eid) == {}

    def test_corrupt_results_file_raises(self, run: Run) -> None:
        with run.start() as ctx:
            eid = ctx.id
        _results_file(run, eid).write_text("{not json")
        with pytest.raises(ValueError, match=r"results\.json"):
            run.results(eid)

    def test_non_dict_results_raises(self, run: Run) -> None:
        with run.start() as ctx:
            eid = ctx.id
        _results_file(run, eid).write_text('{"schema_version": 3, "results": [1]}')
        with pytest.raises(ValueError, match=r"results\.json"):
            run.results(eid)

    def test_returns_a_copy(self, run: Run) -> None:
        with run.start() as ctx:
            ctx.set_result("a", 1)
            eid = ctx.id
        first = run.results(eid)
        first["a"] = 99
        first["b"] = 2
        assert run.results(eid) == {"a": 1}

    def test_reads_through_workspace_fs(self, tmp_path: Path) -> None:
        from molab.workspace.fs_local import LocalFileSystem
        from tests.support.counting_fs import CountingFileSystem

        fs = CountingFileSystem(LocalFileSystem())
        ws = Workspace(tmp_path / "ws", name="lab", fs=fs)  # type: ignore[arg-type]
        run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
        with run.start() as ctx:
            ctx.set_result("a", 1)
            eid = ctx.id
        fs.reset()
        assert run.results(eid) == {"a": 1}
        assert fs.for_basename("results.json", "open") == 1


class TestRunGetResult:
    def test_driver_result_wins_and_skips_seam(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            ctx.set_result("train", "driver-value")
            eid = ctx.id
        stub_executor.outputs[eid] = {"train": "node"}
        assert run.get_result("train", execution_id=eid) == "driver-value"
        assert stub_executor.calls == []

    def test_driver_none_does_not_fall_back(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            ctx.set_result("train", None)
            eid = ctx.id
        stub_executor.outputs[eid] = {"train": "node"}
        assert run.get_result("train", execution_id=eid) is None
        assert stub_executor.calls == []

    def test_falls_back_to_seam_outputs(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            eid = ctx.id
        assert eid == "e01"
        stub_executor.outputs["e01"] = {"train": {"loss": 0.125}}
        assert run.get_result("train", execution_id="e01") == {"loss": 0.125}
        assert stub_executor.calls == [(run.id, "e01")]

    def test_selected_execution_is_passed_through(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            old = ctx.id
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            new = ctx.id
        stub_executor.outputs[old] = {"train": "old"}
        stub_executor.outputs[new] = {"train": "new"}
        assert run.get_result("train", execution_id=old) == "old"
        assert run.get_result("train", execution_id=new) == "new"
        assert stub_executor.calls == [(run.id, old), (run.id, new)]

    def test_unknown_key_returns_none(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            eid = ctx.id
        stub_executor.outputs[eid] = {"train": 1}
        assert run.get_result("other", execution_id=eid) is None

    def test_does_not_parse_the_journal(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            eid = ctx.id
        journal = Path(str(run.execution_dir(eid))) / "workflow.json"
        journal.write_text("{not json")
        stub_executor.outputs[eid] = {"train": 1}
        assert run.get_result("train", execution_id=eid) == 1

    def test_cancel_preserves_driver_results(self, run: Run, stub_executor) -> None:
        with run.start() as ctx:
            ctx.set_result("train", "driver-value")
            eid = ctx.id
            run.cancel(eid)
        assert run.get_result("train", execution_id=eid) == "driver-value"
        assert run.executions[-1].status is ExecutionStatus.CANCELLED
