"""A worker's report and its brief round-trip through the knowledge routes."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from molab.workspace import Experiment, Run, Workspace

ServedFactory = Callable[..., TestClient]
RunFixture = tuple[Workspace, Experiment, Run]

DIGEST = hashlib.sha256(b"the brief").hexdigest()


def _host(ws: Workspace, exp: Experiment) -> str:
    return Path(str(exp.resolve())).relative_to(Path(str(ws.root))).as_posix()


def _report() -> dict[str, object]:
    return {
        "kind": "worker_report",
        "delegation": "projects/p/knowledges/study.md",
        "attempt": "a1",
        "brief": "projects/p/experiments/e/knowledges/brief-r1.md",
        "brief_digest": DIGEST,
        "outcome": "partial",
        "summary": "Trimer built; decamer not attempted.",
        "checks": {"trimer_atoms": {"verdict": "pass", "value": 205}},
        "products": [{"path": "projects/p/experiments/e/scratch/trimer.pdb", "kind": "structure"}],
        "protocol_deviations": [{"item": "seed", "expected": "42", "actual": "7"}],
        "capability_gaps": [
            {"component": "molpy", "title": "no port-aware join", "repro": "mp.join(a, b)"}
        ],
        "next": "Build the decamer.",
    }


def _brief() -> dict[str, object]:
    return {
        "kind": "brief",
        "delegation": "projects/p/knowledges/study.md",
        "round": 1,
        "digest": DIGEST,
        "inputs": ["projects/p/knowledges/plan.md"],
        "protocol": {"reproduce": "molab:execution/e20", "seed": 42},
    }


def _create(client: TestClient, exp: Experiment, host: str, **body: object) -> dict[str, object]:
    response = client.post(
        "/api/knowledge/doc",
        json={
            "hostPath": host,
            "sources": [{"kind": "experiment", "ref": exp.id}],
            **body,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestWorkerRecordRoutes:
    def test_a_worker_report_round_trips(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            created = _create(
                client,
                exp,
                _host(ws, exp),
                name="Round 1 report",
                cls="Report",
                createdBy="worker",
                body="# Round 1\n",
                record=_report(),
            )
            assert created["cls"] == "Report"
            got = client.get("/api/knowledge/doc/record", params={"path": created["relPath"]})
        assert got.status_code == 200, got.text
        assert got.json()["cls"] == "Report"
        assert got.json()["record"] == _report()
        assert len(got.json()["digest"]) == 64

    def test_a_brief_round_trips(self, served: ServedFactory, fresh_run: RunFixture) -> None:
        ws, exp, _run = fresh_run
        with served(ws) as client:
            created = _create(
                client,
                exp,
                _host(ws, exp),
                name="Brief r1",
                cls="Note",
                createdBy="tack",
                body="the brief",
                record=_brief(),
            )
            got = client.get("/api/knowledge/doc/record", params={"path": created["relPath"]})
        assert got.status_code == 200, got.text
        assert got.json()["record"] == _brief()

    def test_the_wrong_class_or_an_invalid_record_is_422(
        self, served: ServedFactory, fresh_run: RunFixture
    ) -> None:
        ws, exp, _run = fresh_run
        host = _host(ws, exp)
        with served(ws) as client:
            misplaced = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Brief",
                    "cls": "Report",
                    "hostPath": host,
                    "sources": [{"kind": "experiment", "ref": exp.id}],
                    "record": _brief(),
                },
            )
            invalid = client.post(
                "/api/knowledge/doc",
                json={
                    "name": "Round 1 report",
                    "cls": "Report",
                    "hostPath": host,
                    "sources": [{"kind": "experiment", "ref": exp.id}],
                    "record": {**_report(), "outcome": "nearly"},
                },
            )
        assert misplaced.status_code == 422, misplaced.text
        assert "belongs on a Note, not a Report" in misplaced.text
        assert invalid.status_code == 422, invalid.text
        assert "outcome" in invalid.text
        assert not (Path(str(ws.root)) / host / "knowledges" / "round-1-report.md").exists()
