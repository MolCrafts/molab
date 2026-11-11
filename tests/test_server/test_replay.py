"""Research replay reads real git/attempt evidence without changing the workspace."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from molab.knowledge import Delegation, Plan
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.write import write_knowledge
from molab.services.replay import research_replay
from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.history import GitHistory


@pytest.fixture
def study(tmp_path):
    ws = Workspace(tmp_path / "ws", name="replay")
    ws.materialize()
    assert GitHistory(ws.root).init()
    exp = ws.add_project("project").add_experiment("experiment")
    a = exp.add_run(params={"model": "a"})
    b = exp.add_run(params={"model": "b"})
    with a.start() as ctx:
        ctx.mark_failed("out of memory")
    with b.start() as ctx:
        ctx.mark_succeeded()
    with a.start(mode=ExecutionMode.RESUME, predecessor="e01") as ctx:
        ctx.mark_succeeded()
    return ws, exp, a, b


def test_failure_then_resume_are_ordered_qualified_and_read_only(study, served):
    ws, _, a, _ = study
    history = GitHistory(ws.root)
    before = [(p, p.read_bytes()) for p in Path(str(ws.root)).rglob("execution.json")]
    commits = [entry.commit for entry in history.entries()]
    with served(ws) as client:
        response = client.get("/api/history/replay", params={"limit": 200})
    assert response.status_code == 200
    page = response.json()
    events = page["events"]
    assert [event["at"] for event in events] == sorted(event["at"] for event in events)
    created = [event for event in events if event["action"] == "ExecutionCreated"]
    assert len(created) == 3
    assert len({event["ref"] for event in created}) == 3
    failures = [event for event in events if event["details"].get("status") == "failed"]
    assert len(failures) == 1 and failures[0]["details"]["error"]
    resumed = next(event for event in created if event["details"]["mode"] == "resume")
    assert resumed["details"]["basedOnExecutionId"] == "e01"
    assert resumed["ref"].endswith(f"/run/{a.id}/execution/e02")
    assert events.index(failures[0]) < events.index(resumed)
    assert sum(event["action"] == "experiment.created" for event in events) == 1
    assert not any(event["action"] == "ExperimentCreated" for event in events)
    assert all(p.read_bytes() == data for p, data in before)
    assert [entry.commit for entry in history.entries()] == commits


def test_pages_cover_the_same_chronology_without_duplicates(study, served):
    ws, *_ = study
    with served(ws) as client:
        first = client.get("/api/history/replay", params={"limit": 2}).json()
        events = list(first["events"])
        offset = first["nextOffset"]
        while offset is not None:
            page = client.get(
                "/api/history/replay", params={"limit": 2, "offset": offset, "asOf": first["asOf"]}
            ).json()
            events.extend(page["events"])
            offset = page["nextOffset"]
        complete = client.get(
            "/api/history/replay", params={"limit": 200, "asOf": first["asOf"]}
        ).json()
    assert events == complete["events"]
    assert len(events) == len({event["id"] for event in events}) == first["total"]


def test_global_experiment_and_run_filters_include_only_their_products(study, served):
    ws, exp, a, b = study
    with a.start(mode=ExecutionMode.RERUN) as ctx:
        ctx.register({"model": "a"}, title="a.json")
        ctx.mark_succeeded()
    with b.start(mode=ExecutionMode.RERUN) as ctx:
        ctx.register({"model": "b"}, title="b.json")
        ctx.mark_succeeded()
    with served(ws) as client:
        experiment = client.get(
            "/api/history/replay", params={"experimentId": exp.id, "limit": 200}
        )
        assert experiment.status_code == 200
        run = client.get("/api/history/replay", params={"runId": a.id, "limit": 200})
        assert run.status_code == 200
        assert a.id in run.text and b.id not in run.text
        assert [event["title"] for event in run.json()["events"] if event["kind"] == "asset"] == [
            "a.json"
        ]


def test_saved_attempts_fill_missing_git_events(study, monkeypatch):
    ws, _, _, _ = study
    monkeypatch.setattr(GitHistory, "entries", lambda *_args, **_kwargs: [])
    page = research_replay(ws, kind="execution", limit=200)
    assert len(page.events) == 9
    assert all(event.commit is None for event in page.events)


def test_no_git_still_has_execution_replay_and_explicit_coverage(study):
    ws, *_ = study
    shutil.rmtree(Path(str(ws.root)) / ".git")
    page = research_replay(ws, kind="execution", limit=200)
    assert len(page.events) == 9
    assert not page.history_available
    assert page.warnings


def test_plan_snapshot_is_historical_even_after_rewrite_and_delete(study, served):
    ws, exp, *_ = study
    doc = write_knowledge(
        exp,
        name="Protocol",
        of=Plan,
        sources=[SourceRef.of(exp)],
        created_by="scientist",
        text="Original protocol: seed 7",
    )
    first = next(
        e
        for e in research_replay(ws, kind="knowledge", limit=200).events
        if e.action == "knowledge.created"
    )
    write_knowledge(
        exp,
        name="Protocol",
        of=Plan,
        sources=[SourceRef.of(exp)],
        created_by="scientist",
        text="Revised protocol: seed 42",
    )
    doc.delete()
    with served(ws) as client:
        response = client.get(
            "/api/history/replay/document",
            params={"commit": first.commit, "document": first.document},
        )
    assert response.status_code == 200
    assert "seed 7" in response.json()["body"]
    assert "seed 42" not in response.json()["body"]


def test_delegation_decisions_are_replayed_once_from_their_recorded_version(study):
    ws, exp, *_ = study
    decision = {
        "at": datetime.now(UTC).isoformat(),
        "name": "Reduce batch",
        "kind": "revise",
        "reason": "The first attempt ran out of memory",
        "evidence": [],
    }
    record = {"goal": "Replay", "scope": str(SourceRef.of(exp).ref), "decisions": [decision]}
    for body in ["First version", "Later status update"]:
        write_knowledge(
            exp,
            name="Supervision",
            of=Delegation,
            sources=[SourceRef.of(exp)],
            record=record,
            created_by="tack",
            text=body,
        )
    events = [
        event
        for event in research_replay(ws, limit=200).events
        if event.action == "research.decision"
    ]
    assert len(events) == 1
    assert events[0].title == decision["name"]
    assert events[0].details["reason"] == decision["reason"]
    assert "First version" in GitHistory(ws.root).show(events[0].commit, events[0].document)


def test_experiment_boundary_excludes_sibling_runs_and_documents(study, served):
    ws, exp, a, b = study
    sibling = ws.get_project("project").add_experiment("private-sibling")
    other = sibling.add_run(params={"secret": 1})
    with other.start() as ctx:
        ctx.mark_succeeded()
    write_knowledge(
        sibling,
        name="Private protocol",
        of=Plan,
        sources=[SourceRef.of(sibling)],
        created_by="scientist",
        text="private contents",
    )
    with served(SimpleNamespace(root=exp.experiment_dir)) as client:
        response = client.get("/api/history/replay", params={"limit": 200})
        assert response.status_code == 200
        assert other.id not in response.text
        assert "Private protocol" not in response.text
        assert a.id in response.text and b.id in response.text
        bad = client.get(
            "/api/history/replay/document",
            params={
                "commit": "a" * 40,
                "document": "../private-sibling/knowledges/private-protocol.md",
            },
        )
        assert bad.status_code == 422


@pytest.mark.parametrize(
    "params", [{"offset": -1}, {"limit": 201}, {"kind": "execute"}, {"asOf": "2026-11-10T00:00:00"}]
)
def test_bad_replay_query_is_refused_without_execution(study, served, params):
    ws, _, a, _ = study
    with served(ws) as client:
        assert client.get("/api/history/replay", params=params).status_code == 422
    assert len(a.executions) == 2


def test_document_history_includes_manual_git_edits_and_compares_without_writing(study, served):
    import subprocess

    ws, exp, *_ = study
    doc = write_knowledge(
        exp,
        name="Versioned claim",
        of=Plan,
        sources=[SourceRef.of(exp)],
        created_by="scientist",
        text="Original claim\n",
    )
    path = Path(str(doc.path))
    relative = path.relative_to(Path(str(ws.root))).as_posix()
    path.write_text(
        path.read_text(encoding="utf-8").replace("Original claim", "Manually revised claim"),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "--", relative], cwd=ws.root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Scientist",
            "-c",
            "user.email=s@example.test",
            "commit",
            "-m",
            "Review the claim outside Molab",
        ],
        cwd=ws.root,
        check=True,
        capture_output=True,
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace("Manually revised claim", "Uncommitted review"),
        encoding="utf-8",
    )
    before = path.read_bytes()
    with served(ws) as client:
        page = client.get("/api/history/document", params={"document": relative})
        assert page.status_code == 200
        revisions = page.json()["revisions"]
        assert revisions[0]["summary"] == "Review the claim outside Molab"
        version = client.get(
            "/api/history/document",
            params={
                "document": relative,
                "commit": revisions[0]["commit"],
            },
        )
        assert version.status_code == 200
        assert "Manually revised claim" in version.json()["body"]
        assert "-Manually revised claim" in version.json()["diff"]
        assert "+Uncommitted review" in version.json()["diff"]
        assert (
            client.get(
                "/api/history/document",
                params={
                    "document": relative,
                    "commit": "f" * 40,
                },
            ).status_code
            == 404
        )
    assert path.read_bytes() == before


def test_document_history_refuses_escape_nonknowledge_and_sibling_versions(study, served):
    _ws, exp, *_ = study
    write_knowledge(
        exp,
        name="Visible",
        of=Plan,
        sources=[SourceRef.of(exp)],
        created_by="scientist",
        text="Visible",
    )
    with served(SimpleNamespace(root=exp.experiment_dir)) as client:
        for path in ("../private/knowledges/secret.md", "/knowledges/secret.md", "index.md"):
            assert client.get("/api/history/document", params={"document": path}).status_code == 422
        assert (
            client.get(
                "/api/history/document",
                params={
                    "document": "knowledges/visible.md",
                    "commit": "HEAD",
                },
            ).status_code
            == 422
        )
        page = client.get("/api/history/document", params={"document": "knowledges/visible.md"})
        assert page.status_code == 200 and page.json()["revisions"]
        assert (
            client.get(
                "/api/history/document",
                params={
                    "document": "knowledges/visible.md",
                    "commit": page.json()["revisions"][0]["commit"],
                },
            ).status_code
            == 200
        )


def test_document_history_without_git_reports_unavailable(tmp_path, served):
    ws = Workspace(tmp_path / "without-history", name="No history")
    ws.materialize()
    shutil.rmtree(Path(str(ws.root)) / ".git", ignore_errors=True)
    with served(ws) as client:
        response = client.get(
            "/api/history/document", params={"document": "knowledges/untracked.md"}
        )
        assert response.status_code == 200
        assert response.json()["available"] is False
        assert response.json()["revisions"] == []
