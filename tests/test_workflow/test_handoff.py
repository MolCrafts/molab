"""A later run reuses an earlier workflow's outputs and cache."""

from __future__ import annotations

from pathlib import Path

import molab as me
from molab.workflow import Workflow
from molab.workflow.cache_store import FileCacheStore, ReadThroughCacheStore


def _pipeline(calls: list[str]) -> Workflow:
    wf = Workflow(name="pipeline")

    @wf.task
    def build(x: int) -> int:
        calls.append("build")
        return x + 1

    @wf.task(depends_on=["build"])
    def use(build: int) -> int:
        calls.append("use")
        return build * 2

    return wf


def test_resume_from_skips_tasks_the_earlier_run_finished(tmp_path: Path) -> None:
    calls: list[str] = []
    ws = me.Workspace(tmp_path / "ws", name="lab")
    project = ws.add_project("demo")
    earlier = project.add_experiment("monomers").add_run(params={"x": 3})
    later = project.add_experiment("equilibrate").add_run(params={"x": 3})
    workflow = _pipeline(calls)

    first = earlier.execute(workflow)
    assert calls == ["build", "use"]
    assert first.outputs["use"] == 8

    second = later.execute(workflow, resume_from=earlier)
    assert calls == ["build", "use"]
    assert second.outputs["build"] == 4
    assert second.outputs["use"] == 8


def test_read_through_copies_a_hit_into_the_front_store(tmp_path: Path) -> None:
    back = FileCacheStore(tmp_path / "earlier")
    front = FileCacheStore(tmp_path / "later")
    back.write("task-key", '{"n": 1}')

    store = ReadThroughCacheStore(front, back)

    assert store.read("task-key") == '{"n": 1}'
    assert front.read("task-key") == '{"n": 1}'
    store.write("fresh", '{"n": 2}')
    assert back.read("fresh") is None
