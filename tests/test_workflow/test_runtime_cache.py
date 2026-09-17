"""Runtime ↔ ``Caching`` wiring (spec workflow-refactor-04-runtime-flat-cache).

``Caching`` identity is unit-tested in ``test_cache_contract``; this file proves
the runtime actually *calls* it — one orthogonal wiring behaviour per test:
hit serves the cached output, hit re-registers the artifact, config discriminates
the key, ``cache=None`` disables caching, actors are never cached, and a failing
backend degrades gracefully but visibly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workflow import (
    Caching,
    Task,
    TaskContext,
    Workflow,
    WorkflowCompiler,
    WorkflowRuntime,
)
from molab.workspace import Workspace

# ── module-level per-task execution counters (bodies increment these) ───────
_COUNTERS: dict[str, int] = {}


def _bump(name: str) -> int:
    _COUNTERS[name] = _COUNTERS.get(name, 0) + 1
    return _COUNTERS[name]


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    _COUNTERS.clear()


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "lab")
    ws.materialize()
    return ws


def _new_run(workspace: Workspace, name: str):
    project = workspace.add_project(name=f"p-{name}")
    experiment = project.add_experiment(name=f"e-{name}")
    return experiment.add_run(params={})


def _run_artifacts(run, *, name: str | None = None):
    artifacts = run._execution_repository().get(run.executions[-1].id).artifacts
    if name is not None:
        artifacts = [a for a in artifacts if a.name == name]
    return artifacts


class _FailingPutStore:
    """A CacheStore whose writes always fail (full disk / permissions shape)."""

    def read(self, key: str) -> str | None:
        return None

    def write(self, key: str, content: str) -> None:
        raise OSError("disk full")

    def remove(self, key: str) -> bool:
        return False

    def keys(self):
        return iter(())

    def access_time(self, key: str) -> float:
        return 0.0

    def touch(self, key: str) -> None:
        return None

    def total_bytes(self) -> int:
        return 0

    def clear(self) -> int:
        return 0


@pytest.mark.asyncio
class TestRuntimeCaching:
    async def test_second_run_hits_cache_and_serves_output_without_recompute(
        self, workspace: Workspace
    ) -> None:
        wf = Workflow(name="counted")

        @wf.task
        async def step(ctx: TaskContext) -> int:
            _bump("step")
            return 42

        compiled = WorkflowCompiler().compile(wf)
        cache = Caching(store=workspace.cache.as_cache_store())

        run1 = _new_run(workspace, "run1")
        with run1.start() as ctx1:
            r1 = await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        assert r1.outputs["step"] == 42
        assert _COUNTERS["step"] == 1

        run2 = _new_run(workspace, "run2")
        with run2.start() as ctx2:
            r2 = await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)
        # Body must NOT have run again — the cached output is served verbatim.
        assert r2.outputs["step"] == 42
        assert _COUNTERS["step"] == 1

    async def test_auto_cache_from_run_context_writes_under_molab_cache(
        self, workspace: Workspace
    ) -> None:
        wf = Workflow(name="auto-cache")

        @wf.task
        async def step(ctx: TaskContext) -> int:
            _bump("auto")
            return 7

        compiled = WorkflowCompiler().compile(wf)
        run = _new_run(workspace, "auto")
        with run.start() as ctx:
            result = await WorkflowRuntime().execute(compiled, run_context=ctx)
        assert result.outputs["step"] == 7
        # Machine state lives under .molab/, never inside a scientific dir.
        cache_root = Path(workspace.root) / ".molab" / "cache"
        assert cache_root.is_dir()
        assert list(cache_root.glob("*/*.json"))
        assert not (Path(run.run_dir) / "cache").exists()
        assert not (Path(workspace.root) / "cache").exists()

    async def test_artifact_reregistered_on_hit_without_recompute(
        self, workspace: Workspace
    ) -> None:
        wf = Workflow(name="artifact-producer")

        @wf.task
        async def produce(ctx: TaskContext) -> str:
            _bump("produce")
            ctx.register_artifact("produced", name="produce.txt")
            return "produced"

        compiled = WorkflowCompiler().compile(wf)
        cache = Caching(store=workspace.cache.as_cache_store())

        run1 = _new_run(workspace, "art1")
        with run1.start() as ctx1:
            await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        assert _COUNTERS["produce"] == 1
        art1 = _run_artifacts(run1, name="produce.txt")
        assert len(art1) == 1
        hash1 = art1[0].content.digest
        assert hash1

        # Second run — cache HIT. The producer body must not run, yet the artifact
        # must be resolvable in run2's scope with a byte-identical content digest.
        run2 = _new_run(workspace, "art2")
        with run2.start() as ctx2:
            await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)
        assert _COUNTERS["produce"] == 1  # no recompute

        art2 = _run_artifacts(run2, name="produce.txt")
        assert len(art2) == 1
        assert art2[0].content.digest == hash1

    async def test_config_change_forces_miss(self, workspace: Workspace) -> None:
        """The runtime threads the compiled snapshot's config identity into the
        cache key: same config → HIT, different config → MISS (body reruns)."""

        class Compute(Task):
            def __init__(self, factor: int = 0) -> None:
                self.factor = factor  # build-time config = cache-identity discriminator

            async def execute(self, ctx: TaskContext) -> int:
                _bump("compute")
                return self.factor * 10

        cache = Caching(store=workspace.cache.as_cache_store())

        def _compiled(factor: int):
            return WorkflowCompiler().compile(
                Workflow(name="cfg").add(Compute(factor), name="compute")
            )

        run1 = _new_run(workspace, "cfg1")
        with run1.start() as ctx1:
            await WorkflowRuntime().execute(_compiled(2), run_context=ctx1, cache=cache)
        assert _COUNTERS["compute"] == 1

        # Same identity + inputs → HIT (no second body run).
        run2 = _new_run(workspace, "cfg2")
        with run2.start() as ctx2:
            await WorkflowRuntime().execute(_compiled(2), run_context=ctx2, cache=cache)
        assert _COUNTERS["compute"] == 1

        # Different config → different snapshot key → MISS (body runs again).
        run3 = _new_run(workspace, "cfg3")
        with run3.start() as ctx3:
            await WorkflowRuntime().execute(_compiled(3), run_context=ctx3, cache=cache)
        assert _COUNTERS["compute"] == 2

    async def test_cache_none_disables_caching(self, tmp_path: Path) -> None:
        # No workspace run_context → nothing to auto-derive a cache from, and
        # cache=None (default) → caching off, identical to pre-spec behaviour.
        wf = Workflow(name="no-cache")

        @wf.task
        async def step(ctx: TaskContext) -> int:
            _bump("step")
            return 1

        compiled = WorkflowCompiler().compile(wf)

        await WorkflowRuntime().execute(compiled, run_dir=tmp_path / "nc1")
        await WorkflowRuntime().execute(compiled, run_dir=tmp_path / "nc2")
        assert _COUNTERS["step"] == 2

    async def test_actor_is_never_cached(self, workspace: Workspace) -> None:
        wf = Workflow(name="actor-wf")

        @wf.actor
        async def streamer(ctx: TaskContext):
            _bump("streamer")
            yield "chunk"

        compiled = WorkflowCompiler().compile(wf)
        cache = Caching(store=workspace.cache.as_cache_store())

        run1 = _new_run(workspace, "act1")
        with run1.start() as ctx1:
            await WorkflowRuntime().execute(compiled, run_context=ctx1, cache=cache)
        run2 = _new_run(workspace, "act2")
        with run2.start() as ctx2:
            await WorkflowRuntime().execute(compiled, run_context=ctx2, cache=cache)
        # Actor bodies are never cached → ran both times.
        assert _COUNTERS["streamer"] == 2

    async def test_failing_cache_put_warns_once_per_task_and_degrades(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A permanently failing cache backend must be VISIBLE: the first put
        failure per (execution, task) logs a WARNING (not debug), while the run
        itself degrades gracefully and completes uncached."""
        from molab.workflow._engine import node_cache

        warned: list[str] = []
        monkeypatch.setattr(node_cache.logger, "warning", lambda msg: warned.append(str(msg)))

        wf = Workflow(name="degraded-cache")

        @wf.task
        async def first(ctx: TaskContext) -> int:
            _bump("first")
            return 1

        @wf.task(depends_on=["first"])
        async def second(first: int) -> int:
            _bump("second")
            return first + 1

        compiled = WorkflowCompiler().compile(wf)
        cache = Caching(store=_FailingPutStore())

        result = await WorkflowRuntime().execute(compiled, cache=cache)
        assert result.status == "succeeded"  # graceful degradation — run unaffected
        assert result.outputs["second"] == 2
        assert _COUNTERS == {"first": 1, "second": 1}

        # Exactly one WARNING per task naming the task and the failure.
        assert len(warned) == 2
        assert any("'first'" in msg and "disk full" in msg for msg in warned)
        assert any("'second'" in msg and "disk full" in msg for msg in warned)
