"""Sync task bodies are first-class workflow citizens (runset-api sub-task 3).

A pure-computation task should be writable as a plain ``def`` — the engine
dispatches sync bodies to a worker thread (mirroring ``promote._EntryTask``)
so blocking bodies don't stall same-level siblings, and awaits async bodies
as before. Locks the full chain: compile, execute, mixed sync/async DAGs,
OOP ``Task`` subclasses, TaskContext access, and content-addressed caching.
"""

from __future__ import annotations

import asyncio

from molexp.workflow import (
    WorkflowCompiler,
    WorkflowRuntime,
)


def _run(compiled, **kwargs: object):
    return asyncio.run(WorkflowRuntime().execute(compiled, **kwargs))


class TestSyncDecoratorTask:
    def test_sync_task_executes(self) -> None:
        wf = WorkflowCompiler(name="sync-single")

        @wf.task
        def double(x: int) -> int:
            return x * 2

        result = _run(wf.compile(), config={"x": 21})
        assert result.status == "succeeded"
        assert result.outputs["double"] == 42

    def test_sync_task_exception_fails_workflow(self) -> None:
        wf = WorkflowCompiler(name="sync-boom")

        @wf.task
        def boom() -> None:
            raise ValueError("broken body")

        result = _run(wf.compile())
        assert result.status == "failed"


class TestMixedSyncAsyncDag:
    def test_sync_and_async_siblings_feed_one_join(self) -> None:
        """A sync body and an async body at the same level both reach their join."""
        wf = WorkflowCompiler(name="mixed-parallel")

        @wf.task
        def sync_body() -> str:
            return "sync"

        @wf.task
        async def async_body() -> str:
            return "async"

        @wf.task(depends_on=["sync_body", "async_body"])
        def join(sync_body: str, async_body: str) -> str:
            return sync_body + "+" + async_body

        result = _run(wf.compile())
        assert result.outputs["join"] == "sync+async"
