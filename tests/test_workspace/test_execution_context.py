"""Unit tests for ``molab.workspace.execution_context`` (``ExecutionContext``).

The public context for one physical Execution of a logical Run
(``RunContext`` is its alias).

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the heartbeat merge: the per-Execution ``alive`` file is
driven through ``molab.workspace.run_heartbeat`` (``touch_alive`` /
``unlink_alive``), i.e. through the workspace ``FileSystem`` — there is no
second raw-``pathlib`` heartbeat implementation on the context.
"""

from __future__ import annotations

import os
import platform
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from molab._typing import JSONValue
from molab.profile import ProfileConfig
from molab.workspace import Run, Workspace
from molab.workspace.domain import Execution, ExecutionMode, ExecutionStatus
from molab.workspace.execution_context import ExecutionContext
from molab.workspace.fs_local import LocalFileSystem
from tests.support.counting_fs import CountingFileSystem


class TestExecutionContextHeartbeat:
    def test_alive_goes_through_workspace_fs(self, tmp_path: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})
        fs.reset()

        with run.start() as ctx:
            execution_id = ctx.id
            assert fs.for_basename("alive", "touch") == 1
            assert fs.for_basename("alive", "remove") == 0

        assert fs.for_basename("alive", "remove") == 1
        assert execution_id == "e01"
        assert not (Path(str(run.run_dir)) / "executions" / "e01" / "alive").exists()

    def test_failed_alive_remove_still_seals(self, tmp_path: Path) -> None:
        # A remote workspace can fail to remove ``alive``; that is a stale
        # heartbeat file, never a reason to skip the seal.
        fs = _AliveRemoveFails(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})

        with run.start() as ctx:
            execution_id = ctx.id

        assert fs.for_basename("alive", "remove") == 1
        assert execution_id == "e01"
        [execution] = run.executions
        assert execution.status is ExecutionStatus.SUCCEEDED
        assert execution.sealed

    def test_failed_alive_remove_does_not_mask_body_error(self, tmp_path: Path) -> None:
        fs = _AliveRemoveFails(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})

        with pytest.raises(RuntimeError, match="body failed"), run.start():
            raise RuntimeError("body failed")

        [execution] = run.executions
        assert execution.status is ExecutionStatus.FAILED
        assert execution.sealed

    def test_heartbeat_loop_survives_touch_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.workspace import execution_context as ctx_mod

        ws = Workspace(tmp_path)
        experiment = ws.add_project("p").add_experiment("e", workflow_source="s.py", params={})
        run = experiment.add_run(params={"seed": 1})
        calls: list[int] = []

        def flaky_touch(_run: object, _execution_id: str) -> None:
            calls.append(1)
            if len(calls) == 1:
                raise OSError("remote touch failed")

        with run.start() as ctx:
            # Patched after entry: the context's own heartbeat thread is
            # already parked on the real 30 s interval; drive a second loop.
            monkeypatch.setattr(ctx_mod, "touch_alive", flaky_touch)
            monkeypatch.setattr(ctx_mod, "HEARTBEAT_INTERVAL_SECONDS", 0.001)
            stop = threading.Event()
            worker = threading.Thread(target=ctx._heartbeat_loop, args=(stop,), daemon=True)
            worker.start()
            deadline = time.monotonic() + 5
            while len(calls) < 3 and time.monotonic() < deadline:
                time.sleep(0.005)
            stop.set()
            worker.join(timeout=5)
        assert len(calls) >= 3

    def test_private_path_helper_removed(self) -> None:
        assert not hasattr(ExecutionContext, "_heartbeat_path")


class TestExecutionContextProvenance:
    """arch-own-02a §5: creation-time facts at create, host/python at start."""

    def test_start_records_host_and_python(self, run: Run) -> None:
        with run.start():
            pass

        [execution] = run.executions
        assert "config_hash" in execution.environment
        assert "python" in execution.environment
        assert execution.environment["host"] == platform.node()
        assert execution.executor["kind"] == "local"
        assert execution.executor["pid"] == os.getpid()

    def test_preallocated_record_gains_start_facts_on_entry(self, run: Run) -> None:
        rec = run.create_execution(environment={"submit_cwd": "/x"})
        assert "python" not in rec.environment

        with run.start(execution_id=rec.id):
            pass

        [execution] = run.executions
        assert execution.environment["submit_cwd"] == "/x"
        assert "python" in execution.environment

    def test_unknown_explicit_id_is_refused_not_created(self, run: Run) -> None:
        with run.start():
            pass

        with pytest.raises(ValueError, match="create_execution"), run.start(execution_id="e09"):
            pass

        assert [x.id for x in run.executions] == ["e01"]
        assert not (Path(str(run.run_dir)) / "executions" / "e09").exists()


class TestExecutionContext:
    """arch-own-02h §1: an explicit id names an existing QUEUED record; its facts are fixed."""

    def test_queued_record_starts_and_seals(self, run: Run) -> None:
        run.create_execution()

        with run.start(execution_id="e01") as ctx:
            assert ctx.id == "e01"
            assert run.execution("e01").status is ExecutionStatus.RUNNING
            assert len(run.executions) == 1

        assert [x.id for x in run.executions] == ["e01"]
        assert run.executions[0].status is ExecutionStatus.SUCCEEDED

    def test_unknown_id_raises_and_creates_nothing(self, run: Run) -> None:
        with pytest.raises(ValueError, match="create_execution"), run.start(execution_id="e09"):
            pass

        assert run.executions == []
        assert not (Path(str(run.run_dir)) / "executions" / "e09").exists()

    @pytest.mark.parametrize(
        ("kwargs", "name"),
        [
            ({"mode": ExecutionMode.RERUN}, "mode"),
            ({"based_on_execution_id": "e01"}, "based_on_execution_id"),
            ({"checkpoint_artifact_id": "a"}, "checkpoint_artifact_id"),
            ({"bypass_cache": True}, "bypass_cache"),
        ],
    )
    def test_creation_args_with_explicit_id_raise_at_call_time(
        self, run: Run, kwargs: dict[str, object], name: str
    ) -> None:
        run.create_execution()

        with pytest.raises(ValueError, match=name):
            run.start(execution_id="e01", **kwargs)

        record = run.execution("e01")
        assert record.status is ExecutionStatus.QUEUED
        assert record.started_at is None

    def test_config_is_the_recorded_one(self, run: Run) -> None:
        run.create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))

        with run.start(execution_id="e01") as ctx:
            assert ctx.config.name == "cpu"
            assert ctx.config.to_dict() == {"k": 1}

    def test_equal_profile_config_is_accepted(self, run: Run) -> None:
        run.create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))

        with run.start(ProfileConfig({"k": 1}, name="cpu"), execution_id="e01") as ctx:
            assert ctx.config.name == "cpu"

    def test_explicit_empty_profile_matches_a_profileless_record(self, run: Run) -> None:
        run.create_execution()

        with run.start(ProfileConfig({}, name=None), execution_id="e01") as ctx:
            assert ctx.config.to_dict() == {}

    def test_equal_hash_with_a_different_dict_shape_is_accepted(self, run: Run) -> None:
        run.create_execution(profile_config=ProfileConfig({"xs": [1, 2]}, name="cpu"))

        with run.start(ProfileConfig({"xs": (1, 2)}, name="cpu"), execution_id="e01"):
            pass

        assert run.execution("e01").status is ExecutionStatus.SUCCEEDED

    @pytest.mark.parametrize(
        "requested",
        [ProfileConfig({"k": 2}, name="cpu"), ProfileConfig({"k": 1}, name="gpu")],
    )
    def test_differing_profile_config_raises_and_leaves_it_queued(
        self, run: Run, requested: ProfileConfig
    ) -> None:
        run.create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))

        with (
            pytest.raises(ValueError, match="profile_config"),
            run.start(requested, execution_id="e01"),
        ):
            pass

        record = run.execution("e01")
        assert record.status is ExecutionStatus.QUEUED
        assert record.started_at is None

    def test_sealed_id_raises_not_queued(self, run: Run) -> None:
        with run.start() as ctx:
            sealed_id = ctx.id

        with pytest.raises(ValueError, match="not queued"), run.start(execution_id=sealed_id):
            pass

    def test_not_queued_is_reported_before_a_config_mismatch(self, run: Run) -> None:
        with run.start(ProfileConfig({"k": 1}, name="cpu")):
            pass

        with (
            pytest.raises(ValueError, match="not queued"),
            run.start(ProfileConfig({"k": 2}, name="cpu"), execution_id="e01"),
        ):
            pass

    def test_start_without_id_allocates_sequential_ids(self, run: Run) -> None:
        with run.start():
            pass
        with run.start(mode=ExecutionMode.RERUN):
            pass

        assert [x.id for x in run.executions] == ["e01", "e02"]


class TestExecutionContextStartOnce:
    """arch-own-02a §5: the locked start decides; a lost race never enters."""

    def test_start_lost_after_precheck_does_not_enter(
        self, run: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rec = run.create_execution()
        ctx2 = run.start(execution_id=rec.id)
        original = ctx2._executions.start

        def racing_start(
            execution_id: str,
            *,
            environment: dict[str, JSONValue] | None = None,
            executor: dict[str, JSONValue] | None = None,
            workflow_digest: str | None = None,
        ) -> Execution:
            # Another process starts the record after ctx2's QUEUED precheck.
            run._execution_repository().start(rec.id)
            return original(
                execution_id,
                environment=environment,
                executor=executor,
                workflow_digest=workflow_digest,
            )

        monkeypatch.setattr(ctx2._executions, "start", racing_start)

        with pytest.raises(ValueError, match="not queued"), ctx2:
            pass

        assert run.execution(rec.id).status is ExecutionStatus.RUNNING
        assert len(run.executions) == 1
        assert not (Path(str(run.run_dir)) / "executions" / rec.id / "alive").exists()


class TestExecutionContextBypassCache:
    """arch-own-02a §5: ``ctx.bypass_cache`` reads the recorded flag."""

    def test_true_when_requested(self, run: Run) -> None:
        with run.start(bypass_cache=True) as ctx:
            assert ctx.bypass_cache is True

    def test_false_by_default(self, run: Run) -> None:
        with run.start() as ctx:
            assert ctx.bypass_cache is False

    def test_false_before_entry(self, run: Run) -> None:
        assert run.start().bypass_cache is False


def _profile_config_hash() -> Callable[[ProfileConfig | None], str | None]:
    """Import ``profile_config_hash`` lazily so a missing symbol fails per test."""
    from molab.workspace.execution_context import profile_config_hash

    return profile_config_hash


_CONSISTENCY_CASES: list[tuple[str, ProfileConfig | None]] = [
    ("none", None),
    ("empty-unnamed", ProfileConfig({}, name=None)),
    ("content-unnamed", ProfileConfig({"a": 1}, name=None)),
    ("empty-named", ProfileConfig({}, name="cpu")),
]


class TestProfileConfigHash:
    """arch-own-02c §0: the one ``config_hash`` rule shared by record and identity."""

    def test_none_is_none(self) -> None:
        assert _profile_config_hash()(None) is None

    def test_empty_unnamed_is_none(self) -> None:
        assert _profile_config_hash()(ProfileConfig({}, name=None)) is None

    def test_unnamed_with_content_is_its_content_hash(self) -> None:
        cfg = ProfileConfig({"a": 1}, name=None)

        assert _profile_config_hash()(cfg) == cfg.content_hash()

    def test_named_empty_is_its_content_hash(self) -> None:
        cfg = ProfileConfig({}, name="cpu")

        assert _profile_config_hash()(cfg) == cfg.content_hash()

    @pytest.mark.parametrize(
        "cfg",
        [cfg for _, cfg in _CONSISTENCY_CASES],
        ids=[case_id for case_id, _ in _CONSISTENCY_CASES],
    )
    def test_matches_create_execution_record(self, run: Run, cfg: ProfileConfig | None) -> None:
        profile_config_hash = _profile_config_hash()

        record = run.create_execution(profile_config=cfg)

        assert record.environment["config_hash"] == profile_config_hash(cfg)

    def test_name_is_not_identity(self) -> None:
        profile_config_hash = _profile_config_hash()

        assert profile_config_hash(ProfileConfig({"a": 1}, name="cpu")) == profile_config_hash(
            ProfileConfig({"a": 1}, name="gpu")
        )
        assert profile_config_hash(ProfileConfig({}, name="cpu")) == profile_config_hash(
            ProfileConfig({}, name="gpu")
        )

    def test_docstring_states_the_hash_is_content_only(self) -> None:
        doc = _profile_config_hash().__doc__

        assert doc is not None
        assert "content" in doc.lower()
        assert "name" in doc.lower()


class _AliveRemoveFails(CountingFileSystem):
    """Counting wrapper whose ``remove`` of the ``alive`` file raises."""

    def remove(self, path: object, *args: object, **kwargs: object) -> None:
        if str(path).rsplit("/", 1)[-1] == "alive":
            self.calls["remove"] += 1
            self.by_basename[("remove", "alive")] += 1
            raise OSError("remote remove failed")
        self._wrap("remove", self._inner.remove)(path, *args, **kwargs)
