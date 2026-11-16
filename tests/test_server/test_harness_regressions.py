"""Real filesystem/API regressions found by the PBIX harness replay."""

from pathlib import Path

import pytest

from molab.knowledge import Hypothesis, Note, Plan, SourceRef
from molab.knowledge.write import write_knowledge
from molab.workflow import Workflow
from molab.workspace.asset_repository import assets_produced_by


def test_mixed_chinese_titles_keep_distinct_record_identities(fresh_run) -> None:
    _ws, experiment, _run = fresh_run
    title = "PBIX 冻结核算回放一致性"
    delegation = write_knowledge(
        experiment,
        name=title,
        of=Hypothesis,
        sources=[SourceRef.of(experiment)],
        created_by="test",
        text="delegate",
        fields={"verdict": "open"},
    )
    original = Path(delegation.path).read_bytes()
    plan = write_knowledge(
        experiment,
        name=title + "计划",
        of=Plan,
        sources=[SourceRef.of(experiment)],
        created_by="test",
        text="plan",
    )
    assert plan.path != delegation.path
    assert Path(delegation.path).read_bytes() == original
    with pytest.raises(ValueError, match="already holds"):
        Plan(delegation.path, sources=[SourceRef.of(experiment)]).write("wrong class")
    assert Path(delegation.path).read_bytes() == original
    assert delegation.frontmatter()["class"] == "Hypothesis"
    with pytest.raises(ValueError, match="already holds"):
        write_knowledge(
            experiment,
            name=title,
            of=Plan,
            sources=[SourceRef.of(experiment)],
            created_by="test",
            text="overwrite",
        )
    assert Path(delegation.path).read_bytes() == original


def test_truncated_titles_do_not_overwrite_a_different_name(fresh_run) -> None:
    _ws, experiment, _run = fresh_run
    item = write_knowledge(experiment, name="a" * 201, of=Note, created_by="test", text="first")
    original = Path(item.path).read_bytes()
    with pytest.raises(ValueError, match="collides"):
        write_knowledge(experiment, name="a" * 200 + "b", of=Note, created_by="test", text="second")
    assert Path(item.path).read_bytes() == original


def test_legacy_mixed_title_is_rewritten_at_its_existing_path(fresh_run) -> None:
    _ws, experiment, _run = fresh_run
    old = write_knowledge(experiment, name="pbix", of=Note, created_by="test", text="old")
    old.write(None, {"name": "PBIX 研究"})
    rewritten = write_knowledge(
        experiment, name="PBIX 研究", of=Note, created_by="test", text="new"
    )
    assert rewritten.path == old.path
    assert rewritten.read() == "new\n"


def test_outputs_and_downloads_are_bounded_by_run_identity(served, fresh_run) -> None:
    ws, experiment, first = fresh_run
    sibling = ws.get_project("p").add_experiment("other").add_run(params={"x": 2})
    assets = []
    for run in (first, sibling):
        with run.start() as ctx:
            assets.append(ctx.register({"run": run.id}, title="metrics.json"))
            ctx.mark_succeeded()
    assert first.executions[0].id == sibling.executions[0].id == "e01"
    assert [a.id for a in assets_produced_by(ws, "e01", run_id=first.id)] == [assets[0].id]
    prefix = f"/api/projects/{experiment.project.id}/experiments/{experiment.id}/runs/{first.id}/executions/e01"
    with served(ws) as client:
        response = client.get(prefix + "/outputs")
        own = client.get(prefix + f"/assets/{assets[0].id}/content")
        other = client.get(prefix + f"/assets/{assets[1].id}/content")
    assert response.status_code == 200, response.text
    assert [a["id"] for a in response.json()["assets"]] == [assets[0].id]
    assert own.status_code == 200
    assert other.status_code == 404


def test_source_preview_separates_declared_and_historical_runs(served, fresh_run) -> None:
    ws, experiment, _run = fresh_run
    experiment.add_run(params={"model": "wet"})
    workflow = Workflow(name="preview")

    @workflow.task
    def sample() -> int:
        return 1

    script = Path(experiment.resolve()) / "workflow.py"
    script.write_text(f"""from molab import Workspace, Workflow
wf = Workflow(name="preview")
@wf.task
def sample(): return 1
if __name__ == "__main__":
    ws = Workspace({str(ws.root)!r})
    ws.get_project("p").get_experiment("e").run(wf, params={{"model": ["dry"]}})
""")
    experiment.bind_workflow(
        "code",
        entrypoint="workflow.py:wf",
        document=workflow.compile().to_graph_ir().model_dump(mode="json"),
    )
    before = {path: path.read_bytes() for path in Path(ws.root).rglob("index.md")}
    url = f"/api/projects/{experiment.project.id}/experiments/{experiment.id}/workflow/dry-run"
    with served(ws) as client:
        response = client.get(url + "?source=code")
        stored = client.get(url + "?source=stored")
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "code"
    assert response.json()["runs"] == [{"params": {"model": "dry"}}]
    assert len(response.json()["registeredRuns"]) == 2
    assert stored.json()["source"] == "stored"
    assert len(stored.json()["runs"]) == 2
    assert {path: path.read_bytes() for path in Path(ws.root).rglob("index.md")} == before
