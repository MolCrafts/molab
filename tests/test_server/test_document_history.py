"""Document history reads git revisions of one knowledge file without writing it."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from molab.knowledge import Plan
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace
from molab.workspace.history import GitHistory


@pytest.fixture
def study(tmp_path):
    ws = Workspace(tmp_path / "ws", name="history")
    ws.materialize()
    assert GitHistory(ws.root).init()
    exp = ws.add_project("project").add_experiment("experiment")
    return ws, exp


def test_document_history_includes_manual_git_edits_and_compares_without_writing(study, served):
    ws, exp = study
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
    _ws, exp = study
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
