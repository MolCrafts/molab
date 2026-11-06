"""A registered file is the next run's input, and a harvest cites the point.

The next run's inputs are the asset ids on the finding. The test does not
pass an id into ``add_run``. The workflow does not import knowledge.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import molab as me
from molab.knowledge.concepts import Finding
from molab.workflow import TaskContext, Workflow, WorkflowRuntime
from molab.workspace.asset_repository import assets_produced_by


def test_a_registered_file_opens_in_the_next_run_and_is_cited(tmp_path: Path) -> None:
    train = Workflow(name="train")

    @train.task
    def train_task(ctx: TaskContext) -> object:
        path = ctx.workdir / "metrics.json"
        path.write_text('{"loss": 0.08}\n', encoding="utf-8")
        return ctx.register(path, title="metrics")

    follow = Workflow(name="read")

    @follow.task
    def read(inputs: tuple[Path, ...], metrics: Path) -> str:
        assert inputs[0] == metrics
        return metrics.read_text(encoding="utf-8")

    ws = me.Workspace(tmp_path, name="cycle")
    experiment = ws.add_project("demo").add_experiment("train")
    run = experiment.add_run()
    with run.start() as ctx:
        trained = asyncio.run(WorkflowRuntime().execute(train.compile(), run_context=ctx))

    produced = assets_produced_by(ws, run.executions[-1].id)
    assert len(produced) == 1
    asset = produced[0]
    assert trained.outputs["train_task"] == asset.ref
    assert asset.ref == f"molab:asset/{asset.id}"

    finding = Finding.harvest(
        run,
        narrative="The training loss reached 0.08.",
        created_by="tester",
        name="train-loss",
        results={"loss": 0.08},
    )
    assert finding.read_cited("/loss") == 0.08
    reopened = Finding(finding.path)
    assert [(source.ref, source.span) for source in reopened.sources if source.kind == "asset"] == [
        (asset.ref, "/loss")
    ]

    follow_run = experiment.add_run(inputs=finding.inputs)
    with follow_run.start() as ctx:
        followed = asyncio.run(WorkflowRuntime().execute(follow.compile(), run_context=ctx))
    assert followed.outputs["read"] == '{"loss": 0.08}\n'
    assert follow_run.inputs == (asset.id,)


def test_a_series_point_is_the_next_runs_input(tmp_path: Path) -> None:
    record = Workflow(name="record")

    @record.task
    def record_task(ctx: TaskContext) -> object:
        path = ctx.workdir / "series.jsonl"
        path.write_text(
            '{"k":"loss","s":1000,"v":0.2}\n{"k":"loss","s":10000,"v":0.08}\n',
            encoding="utf-8",
        )
        return ctx.register(path, title="series")

    follow = Workflow(name="read-series")

    @follow.task
    def read(inputs: tuple[Path, ...]) -> str:
        return inputs[0].read_text(encoding="utf-8")

    ws = me.Workspace(tmp_path, name="series")
    experiment = ws.add_project("demo").add_experiment("series")
    run = experiment.add_run()
    with run.start() as ctx:
        asyncio.run(WorkflowRuntime().execute(record.compile(), run_context=ctx))

    finding = Finding.harvest(
        run,
        narrative="Loss at step 10000 is 0.08.",
        created_by="tester",
        name="series-loss",
        results={"loss": 0.08},
    )
    assert finding.read_cited("loss@10000") == 0.08

    follow_run = experiment.add_run(inputs=finding.inputs)
    with follow_run.start() as ctx:
        followed = asyncio.run(WorkflowRuntime().execute(follow.compile(), run_context=ctx))
    assert '"s":10000' in followed.outputs["read"]
    assert follow_run.inputs == finding.inputs
