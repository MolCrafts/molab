"""Knowledge document versions: git commits of one file, read without writing it."""

from __future__ import annotations

import shutil
import subprocess
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from molab.cli.knowledge_cmd import knowledge_app
from molab.knowledge import Note, Plan
from molab.knowledge.knowledge_item import SourceRef
from molab.knowledge.write import write_knowledge
from molab.services.document_history import document_history, document_version
from molab.workspace import Workspace
from molab.workspace.history import GitHistory


@pytest.fixture
def study(tmp_path):
    ws = Workspace(tmp_path / "ws", name="history")
    ws.materialize()
    assert GitHistory(ws.root).init()
    exp = ws.add_project("project").add_experiment("experiment")
    return ws, exp


def _manual_commit(root: Path, relative: str, message: str) -> None:
    """Commit *relative* the way a person would: plain git, no molab trailers."""
    subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Scientist",
            "-c",
            "user.email=s@example.test",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=root,
        check=True,
    )


def _replace(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


@pytest.fixture
def renamed(study):
    """A Note created, edited, renamed by molab, then edited by a manual commit."""
    ws, _exp = study
    root = Path(str(ws.root))
    note = write_knowledge(ws, name="cooling", of=Note, created_by="scientist", text="First.\n")
    note.write("Second.\n")
    note.rename("cooling notes", within=ws.root)
    path = Path(str(note.path))
    relative = path.relative_to(root).as_posix()
    _replace(path, "Second.", "Third, by hand.")
    _manual_commit(root, relative, "Review the cooling note outside Molab")
    return ws, relative


class TestVersionListing:
    def test_versions_follow_the_rename_and_include_the_manual_commit(self, renamed) -> None:
        ws, relative = renamed
        history = document_history(ws, relative)
        assert history.available is True
        assert history.uncommitted is False
        numbers = [item.number for item in history.versions]
        assert numbers == list(range(len(numbers), 0, -1))
        newest, oldest = history.versions[0], history.versions[-1]
        assert newest.event is None and newest.agent is None
        assert newest.summary == "Review the cooling note outside Molab"
        assert newest.path == relative
        assert oldest.event == "knowledge.created"
        assert oldest.agent is not None
        assert oldest.path == "knowledges/cooling.md"
        events = {item.event for item in history.versions}
        assert "knowledge.created" in events

    def test_each_version_changes_the_content(self, renamed) -> None:
        ws, relative = renamed
        history = document_history(ws, relative)
        texts = [document_version(ws, relative, item.number).text for item in history.versions]
        assert all(left != right for left, right in pairwise(texts))
        assert "First." in texts[-1]
        assert "Third, by hand." in texts[0]

    def test_an_old_version_is_read_at_the_path_it_had(self, renamed) -> None:
        ws, relative = renamed
        read = document_version(ws, relative, 1)
        assert read.version.number == 1
        assert read.file == str(Path(str(ws.root)) / "knowledges" / "cooling.md")
        assert "First." in read.text

    def test_an_edited_working_file_is_an_uncommitted_working_copy(self, renamed) -> None:
        ws, relative = renamed
        path = Path(str(ws.root)) / relative
        _replace(path, "Third, by hand.", "Fourth, unsaved to git.")
        before = path.read_bytes()
        history = document_history(ws, relative, version=1)
        assert history.uncommitted is True
        assert history.versions[0].summary == "Review the cooling note outside Molab"
        assert history.diff is not None
        assert "-First." in history.diff
        assert "+Fourth, unsaved to git." in history.diff
        assert path.read_bytes() == before

    def test_a_never_committed_document_has_only_a_working_copy(self, study) -> None:
        ws, _exp = study
        loose = Path(str(ws.root)) / "knowledges" / "loose.md"
        loose.parent.mkdir(parents=True, exist_ok=True)
        loose.write_text("---\nclass: Note\nname: loose\n---\nNot in git.\n", encoding="utf-8")
        history = document_history(ws, "knowledges/loose.md")
        assert history.available is True
        assert history.versions == []
        assert history.uncommitted is True

    def test_unknown_and_invalid_versions_are_refused(self, renamed) -> None:
        ws, relative = renamed
        with pytest.raises(LookupError):
            document_version(ws, relative, 99)
        with pytest.raises(ValueError):
            document_version(ws, relative, 0)


class TestRoutes:
    def test_history_route_lists_versions_and_diffs_without_writing(self, renamed, served) -> None:
        ws, relative = renamed
        path = Path(str(ws.root)) / relative
        _replace(path, "Third, by hand.", "Uncommitted review")
        before = path.read_bytes()
        with served(ws) as client:
            page = client.get("/api/history/document", params={"document": relative})
            assert page.status_code == 200
            body = page.json()
            assert body["uncommitted"] is True
            assert body["versions"][0]["summary"] == "Review the cooling note outside Molab"
            assert body["versions"][0]["event"] is None
            compared = client.get(
                "/api/history/document", params={"document": relative, "version": 1}
            )
            assert compared.status_code == 200
            assert "+Uncommitted review" in compared.json()["diff"]
            missing = client.get(
                "/api/history/document", params={"document": relative, "version": 99}
            )
            assert missing.status_code == 404
        assert path.read_bytes() == before

    def test_note_route_reads_a_version_in_the_live_shape(self, renamed, served) -> None:
        ws, relative = renamed
        with served(ws) as client:
            live = client.get("/api/knowledge/note", params={"path": relative})
            assert live.status_code == 200
            assert "Third, by hand." in live.json()["body"]
            old = client.get("/api/knowledge/note", params={"path": relative, "version": 1})
            assert old.status_code == 200
            detail = old.json()
            assert set(detail) == set(live.json())
            assert detail["relPath"] == relative
            assert detail["cls"] == "Note"
            assert detail["body"].strip() == "First."
            history = document_history(ws, relative)
            assert detail["updatedAt"] == history.versions[-1].occurred_at
            assert (
                client.get(
                    "/api/knowledge/note", params={"path": relative, "version": 99}
                ).status_code
                == 404
            )
            assert (
                client.get(
                    "/api/knowledge/note", params={"path": relative, "version": 0}
                ).status_code
                == 422
            )

    def test_version_links_resolve_against_the_path_they_had(self, study, served) -> None:
        ws, exp = study
        doc = write_knowledge(
            exp,
            name="Versioned claim",
            of=Plan,
            sources=[SourceRef.of(exp)],
            created_by="scientist",
            text="Original claim\n",
        )
        relative = Path(str(doc.path)).relative_to(Path(str(ws.root))).as_posix()
        with served(ws) as client:
            live = client.get("/api/knowledge/note", params={"path": relative}).json()
            old = client.get("/api/knowledge/note", params={"path": relative, "version": 1}).json()
        assert old["cls"] == "Plan"
        assert old["links"] == live["links"]
        assert old["cards"] == live["cards"]

    def test_refuses_escape_nonknowledge_and_bad_versions(self, study, served) -> None:
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
                assert (
                    client.get("/api/history/document", params={"document": path}).status_code
                    == 422
                )
            assert (
                client.get(
                    "/api/history/document",
                    params={"document": "knowledges/visible.md", "version": "HEAD"},
                ).status_code
                == 422
            )
            page = client.get("/api/history/document", params={"document": "knowledges/visible.md"})
            assert page.status_code == 200 and page.json()["versions"]
            assert (
                client.get(
                    "/api/knowledge/note",
                    params={"path": "knowledges/visible.md", "version": 1},
                ).status_code
                == 200
            )

    def test_without_git_versions_are_unavailable_and_the_live_read_works(
        self, tmp_path, served
    ) -> None:
        ws = Workspace(tmp_path / "without-history", name="No history")
        ws.materialize()
        write_knowledge(ws, name="untracked", of=Note, created_by="scientist", text="Here.\n")
        shutil.rmtree(Path(str(ws.root)) / ".git", ignore_errors=True)
        with served(ws) as client:
            response = client.get(
                "/api/history/document", params={"document": "knowledges/untracked.md"}
            )
            assert response.status_code == 200
            assert response.json()["available"] is False
            assert response.json()["versions"] == []
            live = client.get("/api/knowledge/note", params={"path": "knowledges/untracked.md"})
            assert live.status_code == 200
            old = client.get(
                "/api/knowledge/note",
                params={"path": "knowledges/untracked.md", "version": 1},
            )
            assert old.status_code == 404


class TestCli:
    def test_versions_lists_newest_first(self, renamed) -> None:
        ws, relative = renamed
        result = CliRunner().invoke(knowledge_app, ["versions", relative, "--path", str(ws.root)])
        assert result.exit_code == 0, result.output
        rows = [line.split("\t") for line in result.stdout.splitlines() if line.startswith("v")]
        assert rows[0][0] == f"v{len(rows)}"
        assert rows[0][3] == "manual commit"
        assert rows[-1][0] == "v1" and rows[-1][3] == "knowledge.created"

    def test_read_version_prints_the_old_body(self, renamed) -> None:
        ws, relative = renamed
        result = CliRunner().invoke(
            knowledge_app, ["read", relative, "--version", "1", "--path", str(ws.root)]
        )
        assert result.exit_code == 0, result.output
        assert "First." in result.stdout
        assert "knowledges/cooling.md @ " in result.stdout
        missing = CliRunner().invoke(
            knowledge_app, ["read", relative, "--version", "99", "--path", str(ws.root)]
        )
        assert missing.exit_code == 1
