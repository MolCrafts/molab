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

import hashlib
import json
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
from molab.workspace.artifact_repository import ArtifactRepository
from molab.workspace.domain import (
    RESULT_SEMANTIC_TYPE,
    Execution,
    ExecutionMode,
    ExecutionStatus,
)
from molab.workspace.execution_context import ExecutionContext
from molab.workspace.fs_local import LocalFileSystem
from tests.support.counting_fs import CountingFileSystem


class TestExecutionContextHeartbeat:
    def test_alive_goes_through_workspace_fs(self, tmp_path: Path) -> None:
        fs = CountingFileSystem(LocalFileSystem())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", params={})
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
        experiment = ws.add_project("p").add_experiment("e", params={})
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
        experiment = ws.add_project("p").add_experiment("e", params={})
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
        experiment = ws.add_project("p").add_experiment("e", params={})
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
        rec = run._create_execution(environment={"submit_cwd": "/x"})
        assert "python" not in rec.environment

        with run.start(execution_id=rec.id):
            pass

        [execution] = run.executions
        assert execution.environment["submit_cwd"] == "/x"
        assert "python" in execution.environment

    def test_unknown_explicit_id_is_refused_not_created(self, run: Run) -> None:
        with run.start():
            pass

        with pytest.raises(ValueError, match="does not exist"), run.start(execution_id="e09"):
            pass

        assert [x.id for x in run.executions] == ["e01"]
        assert not (Path(str(run.run_dir)) / "executions" / "e09").exists()


class TestExecutionContext:
    """arch-own-02h §1: an explicit id names an existing QUEUED record; its facts are fixed."""

    def test_queued_record_starts_and_seals(self, run: Run) -> None:
        run._create_execution()

        with run.start(execution_id="e01") as ctx:
            assert ctx.id == "e01"
            assert run.execution("e01").status is ExecutionStatus.RUNNING
            assert len(run.executions) == 1

        assert [x.id for x in run.executions] == ["e01"]
        assert run.executions[0].status is ExecutionStatus.SUCCEEDED

    def test_unknown_id_raises_and_creates_nothing(self, run: Run) -> None:
        with pytest.raises(ValueError, match="does not exist"), run.start(execution_id="e09"):
            pass

        assert run.executions == []
        assert not (Path(str(run.run_dir)) / "executions" / "e09").exists()

    @pytest.mark.parametrize(
        ("kwargs", "name"),
        [
            ({"mode": ExecutionMode.RERUN}, "mode"),
            ({"predecessor": "e01"}, "predecessor"),
            ({"checkpoint": "a"}, "checkpoint"),
            ({"bypass_cache": True}, "bypass_cache"),
        ],
    )
    def test_creation_args_with_explicit_id_raise_at_call_time(
        self, run: Run, kwargs: dict[str, object], name: str
    ) -> None:
        run._create_execution()

        with pytest.raises(ValueError, match=name):
            run.start(execution_id="e01", **kwargs)

        record = run.execution("e01")
        assert record.status is ExecutionStatus.QUEUED
        assert record.started_at is None

    def test_config_is_the_recorded_one(self, run: Run) -> None:
        run._create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))

        with run.start(execution_id="e01") as ctx:
            assert ctx.config.name == "cpu"
            assert ctx.config.to_dict() == {"k": 1}

    def test_equal_profile_config_is_accepted(self, run: Run) -> None:
        run._create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))

        with run.start(ProfileConfig({"k": 1}, name="cpu"), execution_id="e01") as ctx:
            assert ctx.config.name == "cpu"

    def test_explicit_empty_profile_matches_a_profileless_record(self, run: Run) -> None:
        run._create_execution()

        with run.start(ProfileConfig({}, name=None), execution_id="e01") as ctx:
            assert ctx.config.to_dict() == {}

    def test_equal_hash_with_a_different_dict_shape_is_accepted(self, run: Run) -> None:
        run._create_execution(profile_config=ProfileConfig({"xs": [1, 2]}, name="cpu"))

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
        run._create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))

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
        rec = run._create_execution()
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


_DIGEST = "sha256:" + "ab" * 32


class TestExecutionContextExecutionDir:
    """arch-own-03a §4: ``ctx.execution_dir`` derives from ``Run.execution_dir``."""

    def test_equals_the_run_accessor(self, run: Run) -> None:
        with run.start() as ctx:
            assert ctx.execution_dir == run.execution_dir(ctx.id)
            assert ctx.execution_dir.is_dir()

    def test_raises_before_entry(self, run: Run) -> None:
        with pytest.raises(RuntimeError):
            _ = run.start().execution_dir

    def test_layout_literal_is_not_in_the_context_source(self) -> None:
        import inspect

        import molab.workspace.execution_context as module

        assert '"executions"' not in inspect.getsource(module)


class TestExecutionContextConfig:
    """arch-own-03a §1b (D57): ``ctx.config`` is always the record's config."""

    def test_created_context_runs_record_config(self, run: Run) -> None:
        with pytest.raises(RuntimeError), run.start(ProfileConfig({"k": 1}, name="cpu")):
            raise RuntimeError("boom")
        e01_hash = run.execution("e01").environment["config_hash"]

        with run.start(mode=ExecutionMode.RESUME) as ctx:
            assert ctx.config.name == "cpu"
            assert ctx.config.to_dict() == {"k": 1}
            assert run.execution(ctx.id).environment["config_hash"] == e01_hash


class TestExecutionContextWorkflowDigest:
    """arch-own-03a §3: the start transition records the digest."""

    def test_digest_is_recorded_at_start(self, run: Run) -> None:
        with ExecutionContext(run, workflow_digest=_DIGEST) as ctx:
            record = run._execution_repository().get(ctx.id)
            assert record.workflow_digest == _DIGEST
            assert record.status is ExecutionStatus.RUNNING


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

        record = run._create_execution(profile_config=cfg)

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


class TestExecutionContextEmitArtifact:
    def test_second_emit_of_same_name_raises(self, run: Run) -> None:
        with run.start() as ctx:
            first = ctx.emit_artifact(b"one", name="a.txt")
            with pytest.raises(ValueError, match=first.id):
                ctx.emit_artifact(b"two", name="a.txt")
            execution_id = ctx.id
        recorded = run.execution(execution_id).artifacts
        assert [artifact.id for artifact in recorded] == [first.id]
        assert first.content.digest == "sha256:" + hashlib.sha256(b"one").hexdigest()

    def test_user_results_json_and_set_result_do_not_collide(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.emit_artifact(b'{"user": 1}', name="results.json")
            ctx.set_result("k", 1)
        named = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.name == "results.json"
        ]
        assert len(named) == 2
        assert len({artifact.path for artifact in named}) == 2
        assert any(artifact.path.endswith("artifacts/results.json") for artifact in named)
        assert any(artifact.path.endswith("artifacts/_molab/results.json") for artifact in named)
        workspace = run.experiment.project.workspace
        repository = ArtifactRepository(workspace.root, fs=workspace.fs)
        execution_dir = run.execution_dir(execution_id)
        for artifact in named:
            payload = repository.read_bytes(artifact, execution_dir=execution_dir)
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == artifact.content.digest

    def test_public_emit_refuses_reserved(self, run: Run) -> None:
        with run.start() as ctx:
            with pytest.raises(ValueError):
                ctx.emit_artifact({"x": 1}, name="_molab/x.json")
            with pytest.raises(ValueError):
                ctx.emit_artifact(b"x", name="y", semantic_type="result")

    def test_parallel_emits_of_distinct_names_all_recorded(self, run: Run) -> None:
        names = [f"n{index}.txt" for index in range(20)]
        errors: list[BaseException] = []

        def emit_batch(ctx: ExecutionContext, batch: list[str]) -> None:
            try:
                for name in batch:
                    ctx.emit_artifact(name.encode(), name=name)
            except BaseException as exc:
                errors.append(exc)

        with run.start() as ctx:
            workers = [
                threading.Thread(target=emit_batch, args=(ctx, names[offset::4]), daemon=True)
                for offset in range(4)
            ]
            for worker in workers:
                worker.start()
            deadline = time.monotonic() + 45
            for worker in workers:
                remaining = deadline - time.monotonic()
                worker.join(timeout=max(remaining, 0.0))
            assert not any(worker.is_alive() for worker in workers)
            assert errors == []
            recorded = run.execution(ctx.id).artifacts
            assert len(recorded) == 20
            assert {artifact.name for artifact in recorded} == set(names)

    def test_reused_checkpoint_label_is_refused(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            first = ctx.checkpoint("latest", data={"step": 1})
            with pytest.raises(ValueError, match=first.id):
                ctx.checkpoint("latest", data={"step": 2})
        checkpoints = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.semantic_type == "checkpoint"
        ]
        assert len(checkpoints) == 1
        assert checkpoints[0].id == first.id
        saved = json.loads(
            (run.execution_dir(execution_id) / "checkpoints" / "latest.json").read_text(
                encoding="utf-8"
            )
        )
        assert saved["data"] == {"step": 1}
        workspace = run.experiment.project.workspace
        payload = ArtifactRepository(workspace.root, fs=workspace.fs).read_bytes(
            first, execution_dir=run.execution_dir(execution_id)
        )
        assert first.content.digest == "sha256:" + hashlib.sha256(payload).hexdigest()


class TestExecutionContextResults:
    def test_set_result_is_in_memory(self, run: Run) -> None:
        with run.start() as ctx:
            ctx.set_result("energy", -1.5)
            ctx.set_result("energy", -2.25)
            assert ctx.get_result("energy") == -2.25
            execution_id = ctx.id
            assert list(run.execution_dir(execution_id).rglob("results.json")) == []
            assert not (run.execution_dir(execution_id) / "artifacts" / "_molab").exists()
            assert all(
                artifact.semantic_type != RESULT_SEMANTIC_TYPE
                for artifact in run.execution(execution_id).artifacts
            )

    def test_set_result_snapshots_value(self, run: Run) -> None:
        with run.start() as ctx:
            value = {"a": [1]}
            ctx.set_result("v", value)
            value["a"].append(2)
            assert ctx.get_result("v") == {"a": [1]}

    def test_set_result_rejects_non_json(self, run: Run) -> None:
        with run.start() as ctx, pytest.raises(TypeError):
            ctx.set_result("x", object())

    def test_set_result_outside_context_raises(self, run: Run) -> None:
        ctx = run.start()
        with pytest.raises(RuntimeError):
            ctx.set_result("k", 1)

    def test_exit_emits_one_result_artifact(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.set_active_task("train")
            ctx.set_result("energy", -1.5)
            ctx.set_result("converged", True)
            ctx.set_result("energy", -2.25)
        results = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.semantic_type == RESULT_SEMANTIC_TYPE
        ]
        assert len(results) == 1
        artifact = results[0]
        assert artifact.name == "results.json"
        assert artifact.media_type == "application/json"
        assert artifact.path.endswith("artifacts/_molab/results.json")
        assert "task_id" not in artifact.metadata
        workspace = run.experiment.project.workspace
        payload = ArtifactRepository(workspace.root, fs=workspace.fs).read_bytes(
            artifact, execution_dir=run.execution_dir(execution_id)
        )
        assert json.loads(payload) == {"energy": -2.25, "converged": True}

    def test_failed_block_still_emits(self, run: Run) -> None:
        execution_id = ""
        with pytest.raises(ValueError, match="boom"), run.start() as ctx:
            execution_id = ctx.id
            ctx.set_result("k", 1)
            raise ValueError("boom")
        assert run.execution(execution_id).status is ExecutionStatus.FAILED
        results = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.semantic_type == RESULT_SEMANTIC_TYPE
        ]
        assert len(results) == 1
        workspace = run.experiment.project.workspace
        payload = ArtifactRepository(workspace.root, fs=workspace.fs).read_bytes(
            results[0], execution_dir=run.execution_dir(execution_id)
        )
        assert json.loads(payload) == {"k": 1}

    def test_no_set_result_no_artifact(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
        results = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.semantic_type == RESULT_SEMANTIC_TYPE
        ]
        assert results == []

    def test_none_value_is_recorded(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.set_result("k", None)
        results = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.semantic_type == RESULT_SEMANTIC_TYPE
        ]
        assert len(results) == 1
        workspace = run.experiment.project.workspace
        payload = ArtifactRepository(workspace.root, fs=workspace.fs).read_bytes(
            results[0], execution_dir=run.execution_dir(execution_id)
        )
        assert json.loads(payload) == {"k": None}

    def test_externally_sealed_records_no_results(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.set_result("k", 1)
            run.cancel(ctx.id)
        assert run.execution(execution_id).status is ExecutionStatus.CANCELLED
        results = [
            artifact
            for artifact in run.execution(execution_id).artifacts
            if artifact.semantic_type == RESULT_SEMANTIC_TYPE
        ]
        assert results == []
        log = (run.execution_dir(execution_id) / "run.log").read_text(encoding="utf-8")
        assert "results not recorded" in log

    def test_set_result_docstring_states_exit_persistence(self) -> None:
        doc = ExecutionContext.set_result.__doc__
        assert doc is not None
        assert "__exit__" in doc
        assert "checkpoint" in doc
