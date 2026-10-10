"""Unit tests for ``molab.workflow._engine.node_cache``.

``_cache_inputs`` builds the cache ``inputs`` payload — the task's full runtime
identity, now including the effective config (profile data plus any
``dependent_params`` overlay value; the profile name stays out).
``run_task_body_cached`` resolves that effective config exactly once per
execution and keys the cache by it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from molab.profile import ProfileConfig
from molab.workflow import Caching, Workflow, WorkflowCompiler, WorkflowRuntime
from molab.workflow._engine.node_cache import _cache_inputs
from molab.workflow._engine.state import WorkflowState


class TestCacheInputs:
    """``_cache_inputs`` always carries the canonical effective config."""

    def test_plain_task_payload_has_inputs_and_empty_config(self) -> None:
        assert _cache_inputs("t", WorkflowState(), {"a": 1}) == {
            "inputs": {"a": 1},
            "config": {},
        }

    def test_none_and_empty_config_are_one_key(self) -> None:
        state = WorkflowState()
        assert _cache_inputs("t", state, {"a": 1}, config=None) == _cache_inputs(
            "t", state, {"a": 1}, config={}
        )

    def test_profile_config_becomes_a_plain_json_dict(self) -> None:
        payload = _cache_inputs(
            "t", WorkflowState(), None, config=ProfileConfig({"dt": 1.0}, name="a")
        )
        assert payload["config"] == {"dt": 1.0}
        assert type(payload["config"]) is dict
        json.dumps(payload)

    def test_profile_name_is_not_part_of_the_hash_but_data_is(self) -> None:
        state = WorkflowState()

        def digest(data: dict, name: str) -> str:
            payload = _cache_inputs("t", state, None, config=ProfileConfig(data, name=name))
            return Caching._compute_input_hash(payload)

        assert digest({"dt": 1.0}, "a") == digest({"dt": 1.0}, "b")
        assert digest({"dt": 1.0}, "a") != digest({"dt": 2.0}, "a")

    def test_root_inputs_workdir_is_stripped_alongside_config(self) -> None:
        state = WorkflowState()
        state.root_inputs["t"] = {"params": {"x": 1}, "workdir": Path("/w")}
        payload = _cache_inputs("t", state, None, config={"dt": 1.0})
        assert payload["root_inputs"] == {"params": {"x": 1}}
        assert payload["config"] == {"dt": 1.0}

    def test_delivered_value_is_kept_alongside_config(self) -> None:
        payload = _cache_inputs("t", WorkflowState(), None, 5)
        assert payload["delivered"] == 5
        assert payload["config"] == {}


def _dep_workflow(
    overlay: Callable[[dict], dict], counts: dict[str, int], *, name: str = "dep"
) -> object:
    wf = Workflow(name=name)

    def src() -> dict:
        counts["src"] = counts.get("src", 0) + 1
        return {"Tg": 2.0}

    def mech(T: float) -> float:
        counts["mech"] = counts.get("mech", 0) + 1
        return T

    wf.add(src, name="src")
    wf.add(mech, name="mech", depends_on=["src"], dependent_params=overlay)
    return WorkflowCompiler().compile(wf)


def _factor_overlay(factor: float, counts: dict[str, int]) -> Callable[[dict], dict]:
    def overlay(prev: dict) -> dict:
        counts["fn"] = counts.get("fn", 0) + 1
        return {"T": factor * prev["src"].output["Tg"]}

    return overlay


@pytest.mark.asyncio
class TestRunTaskBodyCached:
    """The effective config is resolved once and keys the cache."""

    async def test_dependent_params_called_once_per_execution(self, tmp_path: Path) -> None:
        counts: dict[str, int] = {}
        compiled = _dep_workflow(_factor_overlay(0.5, counts), counts)
        cache = Caching(store_dir=tmp_path / "c")

        first = await WorkflowRuntime().execute(compiled, config={}, cache=cache)
        second = await WorkflowRuntime().execute(compiled, config={}, cache=cache)

        assert first.outputs["mech"] == second.outputs["mech"] == 1.0
        assert counts["fn"] == 2  # one miss + one hit, never twice per execution
        assert counts["mech"] == 1

    async def test_overlay_change_misses(self, tmp_path: Path) -> None:
        counts: dict[str, int] = {}
        low = _dep_workflow(_factor_overlay(0.5, counts), counts)
        high = _dep_workflow(_factor_overlay(2.0, counts), counts)
        assert low.snapshots["mech"].key == high.snapshots["mech"].key
        cache = Caching(store_dir=tmp_path / "c")

        first = await WorkflowRuntime().execute(low, config={}, cache=cache)
        second = await WorkflowRuntime().execute(high, config={}, cache=cache)

        assert first.outputs["mech"] == 1.0
        assert second.outputs["mech"] == 4.0
        assert counts["mech"] == 2

    async def test_non_json_overlay_degrades_gracefully(self, tmp_path: Path) -> None:
        counts: dict[str, int] = {}
        sentinel = object()

        def overlay(prev: dict) -> dict:
            return {"T": 1.0, "obj": sentinel}

        def mech(T: float) -> float:
            counts["mech"] = counts.get("mech", 0) + 1
            return T

        wf = Workflow(name="opaque")
        wf.add(mech, name="mech", dependent_params=overlay)
        compiled = WorkflowCompiler().compile(wf)
        store_dir = tmp_path / "c"
        cache = Caching(store_dir=store_dir)

        first = await WorkflowRuntime().execute(compiled, config={}, cache=cache)
        second = await WorkflowRuntime().execute(compiled, config={}, cache=cache)

        assert first.status == second.status == "succeeded"
        assert first.outputs["mech"] == second.outputs["mech"] == 1.0
        assert counts["mech"] == 2  # not cached, and no error
        assert not list(store_dir.glob("*.json"))


class _BlobStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []

    def put_blob(self, digest: str, data: bytes) -> None:
        self.calls.append((digest, data))


def _lab(tmp_path: Path):
    from molab.workspace import Workspace

    ws = Workspace(tmp_path / "ws", name="lab")
    run = ws.add_project("p").add_experiment("e").add_run()
    return ws, run


class TestPutFileBlobs:
    def test_puts_emitted_bytes(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        from molab.workflow._engine.node_cache import _put_file_blobs

        _ws, run = _lab(tmp_path)
        payload = b"xyz"
        with run.start() as ctx:
            src = ctx.get_dir("work") / "sim.bin"
            src.write_bytes(payload)
            artifact = ctx.emit_artifact(src, name="sim.bin", metadata={"task_id": "sim"})
            store = _BlobStore()
            deps = SimpleNamespace(
                cache=SimpleNamespace(store=store),
                run_context=ctx,
                execution_id=ctx.id,
            )
            _put_file_blobs(deps, [artifact])

        assert store.calls == [(artifact.content.digest, payload)]

    def test_legacy_record_is_read(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        from molab.workflow._engine.node_cache import _put_file_blobs

        workspace, run = _lab(tmp_path)
        payload = b"xyz"
        with run.start() as ctx:
            artifact = ctx.emit_artifact(payload, name="sim.bin", metadata={"task_id": "sim"})
            legacy_path = (
                Path(run.artifact_location(ctx.id, artifact))
                .resolve()
                .relative_to(Path(str(workspace.root)).resolve())
                .as_posix()
            )
            legacy = artifact.model_copy(update={"path": legacy_path})
            store = _BlobStore()
            deps = SimpleNamespace(
                cache=SimpleNamespace(store=store),
                run_context=ctx,
                execution_id=ctx.id,
            )
            _put_file_blobs(deps, [legacy])

        assert store.calls == [(artifact.content.digest, payload)]

    def test_missing_file_and_other_attempt_are_skipped(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        from molab.workflow._engine.node_cache import _put_file_blobs

        _ws, run = _lab(tmp_path)
        with run.start() as ctx:
            artifact = ctx.emit_artifact(b"xyz", name="sim.bin", metadata={"task_id": "sim"})
            (run.execution_dir(ctx.id) / artifact.path).unlink()
            store = _BlobStore()
            deps = SimpleNamespace(
                cache=SimpleNamespace(store=store),
                run_context=ctx,
                execution_id=ctx.id,
            )
            _put_file_blobs(deps, [artifact])
            deps.execution_id = "e02"
            _put_file_blobs(deps, [artifact])

        assert store.calls == []
