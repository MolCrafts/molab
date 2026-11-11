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
from molab.workspace.asset_repository import assets_produced_by
from molab.workspace.domain import (
    Execution,
    ExecutionMode,
    ExecutionOrigin,
    ExecutionStatus,
)
from molab.workspace.execution_context import ExecutionContext
from molab.workspace.fs_local import LocalFS
from tests.support.counting_fs import CountingFileSystem


class TestExecutionContextHeartbeat:
    def test_alive_goes_through_workspace_fs(self, tmp_path: Path) -> None:
        fs = CountingFileSystem(LocalFS())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", params={})
        run = experiment.add_run(params={"seed": 1})
        fs.reset()

        with run.start() as ctx:
            execution_id = ctx.id
            assert fs.for_basename("alive", "touch") == 1
            assert fs.for_basename("alive", "rm") == 0

        assert fs.for_basename("alive", "rm") == 1
        assert execution_id == "e01"
        assert not (Path(str(run.run_dir)) / "executions" / "e01" / "alive").exists()

    def test_failed_alive_remove_still_seals(self, tmp_path: Path) -> None:
        # A remote workspace can fail to remove ``alive``; that is a stale
        # heartbeat file, never a reason to skip the seal.
        fs = _AliveRemoveFails(LocalFS())
        ws = Workspace(tmp_path, fs=fs)
        experiment = ws.add_project("p").add_experiment("e", params={})
        run = experiment.add_run(params={"seed": 1})

        with run.start() as ctx:
            execution_id = ctx.id

        assert fs.for_basename("alive", "rm") == 1
        assert execution_id == "e01"
        [execution] = run.executions
        assert execution.status is ExecutionStatus.SUCCEEDED
        assert execution.sealed

    def test_failed_alive_remove_does_not_mask_body_error(self, tmp_path: Path) -> None:
        fs = _AliveRemoveFails(LocalFS())
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
            workflow_hash: str | None = None,
        ) -> Execution:
            # Another process starts the record after ctx2's QUEUED precheck.
            run._execution_repository().start(rec.id)
            return original(
                execution_id,
                environment=environment,
                executor=executor,
                workflow_hash=workflow_hash,
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
        with ExecutionContext(run, workflow_hash=_DIGEST) as ctx:
            record = run._execution_repository().get(ctx.id)
            assert record.workflow_hash == _DIGEST
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
    """Counting wrapper whose ``rm`` of the ``alive`` file raises."""

    def rm(self, path: object, *args: object, **kwargs: object) -> None:
        if str(path).rsplit("/", 1)[-1] == "alive":
            self.calls["rm"] += 1
            self.by_basename[("rm", "alive")] += 1
            raise OSError("remote remove failed")
        self._wrap("rm", self._inner.rm)(path, *args, **kwargs)


def _produced(run: Run, execution_id: str):
    return assets_produced_by(run.experiment.project.workspace, execution_id)


def _payload(run: Run, asset) -> bytes:
    workspace = run.experiment.project.workspace
    path = workspace.assets_at(asset.scope).payload_path(asset.id)
    return Path(path).read_bytes()


class TestExecutionContextRegister:
    def test_same_bytes_return_the_existing_asset(self, run: Run) -> None:
        with run.start() as ctx:
            first = ctx.register(b"one", title="a.txt")
            again = ctx.register(b"one", title="other.txt")
            execution_id = ctx.id
        assert again.id == first.id
        assert first.ref == f"molab:asset/{first.id}"
        assert [asset.id for asset in _produced(run, execution_id)] == [first.id]
        assert first.content.digest == "sha256:" + hashlib.sha256(b"one").hexdigest()

    def test_new_bytes_replace_the_slot_and_keep_its_id(self, run: Run) -> None:
        with run.start() as ctx:
            first = ctx.register(b"one", title="a.txt")
            second = ctx.register(b"two", title="a.txt")
            execution_id = ctx.id
        assert second.id == first.id
        produced = _produced(run, execution_id)
        assert [asset.content.digest for asset in produced] == [second.content.digest]
        assert second.content.digest != first.content.digest

    def test_a_later_attempt_replaces_the_runs_product(self, run: Run) -> None:
        with run.start() as ctx:
            first = ctx.register(b"one", title="a.txt")
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            second = ctx.register(b"two", title="a.txt")
            later = ctx.id
        assert second.id == first.id
        assert isinstance(second.origin, ExecutionOrigin)
        assert second.origin.execution_id == later
        assets = run.experiment.assets.list()
        assert [asset.id for asset in assets] == [first.id]

    def test_runs_get_their_own_slot_without_numeric_suffixes(self, run: Run) -> None:
        sibling = run.experiment.add_run()
        with run.start() as ctx:
            mine = ctx.register(b"one", title="network.data")
        with sibling.start() as ctx:
            theirs = ctx.register(b"two", title="network.data")
        assert mine.id != theirs.id
        slugs = sorted(
            path.parent.name for path in Path(run.experiment.path, "assets").glob("*/asset.json")
        )
        assert all(slug.endswith("--network-data") for slug in slugs)
        assert not any(slug.endswith("-2") for slug in slugs)

    def test_user_results_title_and_set_result_do_not_collapse(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            user = ctx.register(b'{"user": 1}', title="results.json")
            ctx.set_result("k", 1)
        produced = _produced(run, execution_id)
        assert {asset.title for asset in produced} == {"results.json", "results"}
        assert user.id in {asset.id for asset in produced}
        for asset in produced:
            payload = _payload(run, asset)
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == asset.content.digest

    def test_parallel_registers_of_distinct_bytes_all_land(self, run: Run) -> None:
        names = [f"n{index}.txt" for index in range(20)]
        errors: list[BaseException] = []

        def register_batch(ctx: ExecutionContext, batch: list[str]) -> None:
            try:
                for name in batch:
                    ctx.register(name.encode(), title=name)
            except BaseException as exc:
                errors.append(exc)

        with run.start() as ctx:
            workers = [
                threading.Thread(target=register_batch, args=(ctx, names[offset::4]), daemon=True)
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
            execution_id = ctx.id
        produced = _produced(run, execution_id)
        assert len(produced) == 20
        assert {asset.title for asset in produced} == set(names)

    def test_reused_checkpoint_label_is_refused(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            first = ctx.checkpoint("latest", data={"step": 1})
            with pytest.raises(ValueError, match="latest"):
                ctx.checkpoint("latest", data={"step": 2})
        assert first == run.execution_dir(execution_id) / "checkpoints" / "latest.json"
        saved = json.loads(first.read_text(encoding="utf-8"))
        assert saved["data"] == {"step": 1}
        assert _produced(run, execution_id) == []


class TestExecutionContextResults:
    def test_set_result_is_in_memory(self, run: Run) -> None:
        with run.start() as ctx:
            ctx.set_result("energy", -1.5)
            ctx.set_result("energy", -2.25)
            assert ctx.get_result("energy") == -2.25
            execution_id = ctx.id
            assert list(run.execution_dir(execution_id).rglob("results.json")) == []
            assert _produced(run, execution_id) == []

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

    def test_exit_registers_one_results_asset(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.set_active_task("train")
            ctx.set_result("energy", -1.5)
            ctx.set_result("converged", True)
            ctx.set_result("energy", -2.25)
        results = [asset for asset in _produced(run, execution_id) if asset.title == "results"]
        assert len(results) == 1
        asset = results[0]
        assert asset.media_type == "application/json"
        assert isinstance(asset.origin, ExecutionOrigin)
        assert asset.origin.task is None
        assert json.loads(_payload(run, asset)) == {"energy": -2.25, "converged": True}

    def test_failed_block_still_registers(self, run: Run) -> None:
        execution_id = ""
        with pytest.raises(ValueError, match="boom"), run.start() as ctx:
            execution_id = ctx.id
            ctx.set_result("k", 1)
            raise ValueError("boom")
        assert run.execution(execution_id).status is ExecutionStatus.FAILED
        results = [asset for asset in _produced(run, execution_id) if asset.title == "results"]
        assert len(results) == 1
        assert json.loads(_payload(run, results[0])) == {"k": 1}

    def test_no_set_result_leaves_no_results_asset(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
        assert [asset for asset in _produced(run, execution_id) if asset.title == "results"] == []

    def test_none_value_is_recorded(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.set_result("k", None)
        results = [asset for asset in _produced(run, execution_id) if asset.title == "results"]
        assert len(results) == 1
        assert json.loads(_payload(run, results[0])) == {"k": None}

    def test_externally_sealed_records_no_results(self, run: Run) -> None:
        with run.start() as ctx:
            execution_id = ctx.id
            ctx.set_result("k", 1)
            run.cancel(ctx.id)
        assert run.execution(execution_id).status is ExecutionStatus.CANCELLED
        assert [asset for asset in _produced(run, execution_id) if asset.title == "results"] == []
        log = (run.execution_dir(execution_id) / "run.log").read_text(encoding="utf-8")
        assert "results not recorded" in log

    def test_set_result_docstring_states_exit_persistence(self) -> None:
        doc = ExecutionContext.set_result.__doc__
        assert doc is not None
        assert "__exit__" in doc
        assert "checkpoint" in doc
