"""Cache-identity contract: code_hash + config_hash + inputs_hash.

Architectural lock for ``molab.workflow.cache`` — the cache key is
``f(snapshot.key, inputs_hash)`` and nothing else. Ten pins:

1. ``inputs`` participate in ``cache_key`` — differing inputs ⇒ different key.
2. Identical code + config + inputs collide on one ``cache_key`` (reuse).
3. A ``pathlib.Path`` carried through ``inputs`` hashes stably (no
   memory-address nondeterminism), via the ``_robust_json_default`` Path branch.
4. ``TaskSnapshot.key`` stays ``f"{code_hash}:{config_hash}"`` — ``inputs`` are
   NOT folded into the snapshot identity; the cache, not the snapshot, owns the
   inputs term.
5. Engine-injected root inputs (sweep params) participate in the cache key —
   two runs with different params NEVER share a root-task cache entry.
6. The injected workdir Path does NOT participate — same params with a
   different workdir/execution still HIT.
7. The effective config participates — same params under profile data
   ``{"dt": 1.0}`` and ``{"dt": 2.0}`` MISS.
8. Same params and same config data HIT (across workspaces).
8b. The profile *name* does NOT participate — only its data does.
9. A ``dependent_params`` overlay *value* participates — changing the overlay
   between two attempts of one run MISSES downstream.
10. Execution location does NOT participate — the local-handler and the
    worker shape of one run (the worker takes its config from the record and
    injects no ``run_dir``) share their auto-cache entries.

It also pins the ``Caching`` constructor's ``store`` / ``store_dir`` XOR
validation (moved here from the deleted workspace-backed cache tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.profile import ProfileConfig
from molab.workflow import Task, TaskContext, Workflow, WorkflowCompiler, WorkflowRuntime
from molab.workflow.cache import Caching
from molab.workflow.cache_store import FileCacheStore
from molab.workflow.snapshot import TaskSnapshot
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode


class _Body(Task):
    """A trivial task whose ``__init__`` arg is its build-time config."""

    def __init__(self, k: str = "v") -> None:
        self.k = k

    async def execute(self, ctx: TaskContext) -> dict[str, int]:
        return {"x": 1}


def _snapshot(*, k: str = "v") -> TaskSnapshot:
    # Config is the instance's captured __init__ args — not a registration dict.
    return TaskSnapshot.from_task_body("t", _Body(k))


def _workspace_run(root: Path, name: str, params: dict):
    ws = Workspace(root / f"lab-{name}")
    project = ws.add_project(name="p")
    experiment = project.add_experiment(name="e")
    return experiment.add_run(params=params)


class TestCachingInputHash:
    """``Caching`` folds ``inputs`` (and only inputs) into the cache term."""

    def test_differing_inputs_produce_a_miss(self, tmp_path: Path) -> None:
        """Pin 1 — inputs participate: same snapshot, different inputs ⇒ miss."""
        cache = Caching(store_dir=tmp_path)
        snap = _snapshot()
        cache.put(snap, {"n": 1}, {"result": "A"})
        assert cache.get(snap, {"n": 1}) == {"result": "A"}
        assert cache.get(snap, {"n": 2}) is None

    def test_identical_code_config_inputs_reuse_one_entry(self, tmp_path: Path) -> None:
        """Pin 2 — a fresh snapshot of the same body+config collides and hits."""
        cache = Caching(store_dir=tmp_path)
        snap = _snapshot()
        cache.put(snap, {"n": 1}, {"result": "A"})
        same = _snapshot()
        assert same.key == snap.key
        assert cache.get(same, {"n": 1}) == {"result": "A"}

    def test_input_hash_ignores_key_order(self) -> None:
        """Canonical (sorted) input hashing — insertion order is irrelevant."""
        a = Caching._compute_input_hash({"n": 1, "m": 2})
        b = Caching._compute_input_hash({"m": 2, "n": 1})
        assert a == b

    def test_path_input_hashes_stably_across_instances(self) -> None:
        """Pin 3 — two Path objects for the same path string hash identically
        (``_robust_json_default`` serializes ``str(path)``, not an object repr)."""
        h1 = Caching._compute_input_hash({"workdir": Path("/scratch/abc")})
        h2 = Caching._compute_input_hash({"workdir": Path("/scratch") / "abc"})
        assert h1 == h2

    def test_path_input_distinct_from_equivalent_string(self) -> None:
        """The ``{"__type__": "Path"}`` wrapper keeps ``Path("x")`` distinct from ``"x"``."""
        h_path = Caching._compute_input_hash({"v": Path("x")})
        h_str = Caching._compute_input_hash({"v": "x"})
        assert h_path != h_str


class TestSnapshotExcludesInputs:
    """Pin 4 — ``TaskSnapshot.key`` never folds in runtime inputs."""

    def test_key_moves_with_config_but_never_with_inputs(self) -> None:
        # from_task_body takes no inputs argument: the snapshot cannot know inputs.
        s1 = _snapshot(k="v")
        s2 = _snapshot(k="v")
        assert s1.key == s2.key
        # Build-time config IS part of identity; inputs never reach here.
        s3 = _snapshot(k="other")
        assert s3.key != s1.key


class TestEngineInjectedCacheIdentity:
    """Pins 5 + 6 — engine-injected root inputs: sweep params in, workdir out."""

    @pytest.mark.asyncio
    async def test_differing_run_params_never_share_root_cache(self, tmp_path: Path) -> None:
        """The first sweep cell's root result must NOT be served to
        every other cell. Different run params ⇒ root-task cache MISS ⇒ body runs."""
        counters = {"root": 0}
        wf = Workflow(name="sweep")

        @wf.task
        async def root(ratio: str) -> str:
            counters["root"] += 1
            return ratio

        compiled = WorkflowCompiler().compile(wf)
        cache = Caching(store_dir=tmp_path / "shared-cache")

        run1 = _workspace_run(tmp_path, "a", {"ratio": "r1"})
        with run1.start() as ctx1:
            r1 = await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        run2 = _workspace_run(tmp_path, "b", {"ratio": "r2"})
        with run2.start() as ctx2:
            r2 = await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)

        assert counters["root"] == 2  # both cells computed — no cross-param hit
        assert r1.outputs["root"] == "r1"
        assert r2.outputs["root"] == "r2"  # NOT the first cell's value

    @pytest.mark.asyncio
    async def test_same_params_different_workdir_still_hits(self, tmp_path: Path) -> None:
        """Same params in two workspaces (⇒ different content-addressed workdir
        Paths and execution ids) share one cache entry — workdir never poisons
        the key."""
        counters = {"root": 0}
        wf = Workflow(name="sweep-hit")

        @wf.task
        async def root(ratio: str) -> str:
            counters["root"] += 1
            return ratio

        compiled = WorkflowCompiler().compile(wf)
        cache = Caching(store_dir=tmp_path / "shared-cache")

        run1 = _workspace_run(tmp_path, "ws1", {"ratio": "r1"})
        with run1.start() as ctx1:
            r1 = await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        run2 = _workspace_run(tmp_path, "ws2", {"ratio": "r1"})
        with run2.start() as ctx2:
            r2 = await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)

        assert counters["root"] == 1  # second run served from cache
        assert r1.outputs["root"] == r2.outputs["root"] == "r1"


def _dt_workflow(counters: dict[str, int], name: str = "dt"):
    wf = Workflow(name=name)

    @wf.task
    async def root(ratio: str, dt: float) -> float:
        counters["root"] += 1
        return dt * 10

    return WorkflowCompiler().compile(wf)


def _dependent_workflow(factor: float, counters: dict[str, int]):
    def overlay(prev: dict) -> dict:
        return {"T": factor * prev["src"].output["Tg"]}

    def src() -> dict:
        counters["src"] += 1
        return {"Tg": 2.0}

    def mech(T: float) -> float:
        counters["mech"] += 1
        return T

    wf = Workflow(name="dependent")
    wf.add(src, name="src")
    wf.add(mech, name="mech", depends_on=["src"], dependent_params=overlay)
    return WorkflowCompiler().compile(wf)


class TestEffectiveConfigCacheIdentity:
    """Pins 7-10 — the effective config is in the key; name and location are not."""

    @pytest.mark.asyncio
    async def test_differing_profile_config_misses(self, tmp_path: Path) -> None:
        """Pin 7 — same params, profile ``dt`` 1.0 vs 2.0 ⇒ two body runs."""
        counters = {"root": 0}
        compiled = _dt_workflow(counters)
        cache = Caching(store_dir=tmp_path / "shared-cache")

        run1 = _workspace_run(tmp_path, "a", {"ratio": "r1"})
        with run1.start(ProfileConfig({"dt": 1.0}, name="p")) as ctx1:
            r1 = await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        run2 = _workspace_run(tmp_path, "b", {"ratio": "r1"})
        with run2.start(ProfileConfig({"dt": 2.0}, name="p")) as ctx2:
            r2 = await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)

        assert counters["root"] == 2
        assert r1.outputs["root"] == 10.0
        assert r2.outputs["root"] == 20.0

    @pytest.mark.asyncio
    async def test_same_params_same_config_hits(self, tmp_path: Path) -> None:
        """Pin 8 — equal params and equal config data ⇒ one body run."""
        counters = {"root": 0}
        compiled = _dt_workflow(counters)
        cache = Caching(store_dir=tmp_path / "shared-cache")

        for name in ("ws1", "ws2"):
            run = _workspace_run(tmp_path, name, {"ratio": "r1"})
            with run.start(ProfileConfig({"dt": 1.0}, name="p")) as ctx:
                result = await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)
            assert result.outputs["root"] == 10.0

        assert counters["root"] == 1

    @pytest.mark.asyncio
    async def test_profile_name_alone_does_not_miss(self, tmp_path: Path) -> None:
        """Pin 8b — profile names ``a`` / ``b`` over equal data ⇒ one body run."""
        counters = {"root": 0}
        compiled = _dt_workflow(counters)
        cache = Caching(store_dir=tmp_path / "shared-cache")

        for name in ("a", "b"):
            run = _workspace_run(tmp_path, name, {"ratio": "r1"})
            with run.start(ProfileConfig({"dt": 1.0}, name=name)) as ctx:
                result = await WorkflowRuntime().execute(compiled, run_context=ctx, cache=cache)
            assert result.outputs["root"] == 10.0

        assert counters["root"] == 1

    @pytest.mark.asyncio
    async def test_dependent_params_overlay_change_misses(self, tmp_path: Path) -> None:
        """Pin 9 — overlay factor 0.5 then 2.0 on e01 / e02 of one run ⇒ miss."""
        counters = {"src": 0, "mech": 0}
        cache = Caching(store_dir=tmp_path / "shared-cache")
        run = _workspace_run(tmp_path, "dep", {"ratio": "r1"})

        with run.start() as ctx:
            first = await WorkflowRuntime().execute(
                _dependent_workflow(0.5, counters), run_context=ctx, cache=cache
            )
        with run.start(mode=ExecutionMode.RERUN) as ctx:
            second = await WorkflowRuntime().execute(
                _dependent_workflow(2.0, counters), run_context=ctx, cache=cache
            )

        assert first.outputs["mech"] == 1.0
        assert second.outputs["mech"] == 4.0
        assert counters["mech"] == 2

    @pytest.mark.asyncio
    async def test_local_and_worker_contexts_share_cache(self, tmp_path: Path) -> None:
        """Pin 10 (guard) — local-handler vs worker shape of one run share the
        auto cache: the worker's config comes from the record, with no run_dir."""
        counters = {"root": 0}
        compiled = _dt_workflow(counters)
        run = _workspace_run(tmp_path, "shape", {"ratio": "r1"})
        cfg = ProfileConfig({"dt": 1.0}, name="p")

        run._create_execution(profile_config=cfg)
        with run.start(cfg, execution_id="e01") as ctx:
            local = await WorkflowRuntime().execute(compiled, run_context=ctx)

        run._create_execution(mode=ExecutionMode.RERUN, profile_config=cfg)
        with run.start(execution_id="e02") as ctx:
            assert "run_dir" not in ctx.config
            assert ctx.config.to_dict() == {"dt": 1.0}
            worker = await WorkflowRuntime().execute(compiled, run_context=ctx)

        assert counters["root"] == 1
        assert local.outputs["root"] == worker.outputs["root"] == 10.0


class TestCachingConstructor:
    """``Caching`` takes exactly one of ``store`` / ``store_dir``."""

    def test_rejects_neither_store_nor_dir(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            Caching()

    def test_rejects_both_store_and_dir(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not accept both"):
            Caching(store=FileCacheStore(tmp_path / "store"), store_dir=tmp_path / "fs-cache")
