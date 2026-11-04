"""A dry run walks the graph and does not call task bodies."""

from __future__ import annotations

from molab.workflow import Workflow, WorkflowRuntime


def test_dry_run_orders_waves_and_skips_bodies() -> None:
    calls: list[str] = []
    wf = Workflow(name="pbix")

    @wf.task
    async def monomers() -> dict[str, int]:
        calls.append("monomers")
        return {"n": 1}

    @wf.task
    async def pack() -> dict[str, int]:
        calls.append("pack")
        return {"n": 1}

    @wf.task(depends_on=["monomers", "pack"])
    async def equilibrate(n: int) -> dict[str, int]:
        calls.append("equilibrate")
        return {"n": n}

    report = WorkflowRuntime().dry_run((wf).compile())

    assert calls == []
    assert report.name == "pbix"
    assert report.waves[0].tasks == ("monomers", "pack")
    assert report.waves[1].tasks == ("equilibrate",)
