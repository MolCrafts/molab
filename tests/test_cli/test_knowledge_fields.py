"""``molab knowledge fields``: a document's class fields, read and replaced from the CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from molab.cli.knowledge_cmd import knowledge_app
from molab.knowledge import Note
from molab.knowledge.fields import digest_of
from molab.knowledge.write import write_knowledge
from molab.workspace import Workspace
from molab.workspace.history import GitHistory

DOC = "knowledges/cooling.md"


@pytest.fixture
def lab(tmp_path: Path) -> Workspace:
    workspace = Workspace(root=tmp_path / "lab", name="Test Lab")
    workspace.materialize()
    assert GitHistory(str(workspace.root)).init()
    write_knowledge(workspace, name="cooling", of=Note, created_by="intake", text="Slow.\n")
    return workspace


def _fields(lab: Workspace, *args: str) -> Any:
    return CliRunner().invoke(knowledge_app, ["fields", DOC, *args, "--path", str(lab.root)])


def _note(lab: Workspace) -> Note:
    return Note(Path(str(lab.root)) / DOC)


class TestRead:
    def test_prints_the_fields_and_the_digest_of_the_file(self, lab: Workspace) -> None:
        result = _fields(lab)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["cls"] == "Note"
        # A Note written without a status stores none: the default is not a field on disk.
        assert payload["fields"] == {}
        assert payload["digest"] == digest_of(_note(lab))


class TestSet:
    def test_a_reviewer_sets_a_note_active(self, lab: Workspace) -> None:
        result = _fields(lab, "--set", '{"status": "active"}')
        assert result.exit_code == 0, result.output
        assert _note(lab).fields().status == "active"
        payload = json.loads(result.stdout)
        assert payload["fields"] == {"status": "active"}
        assert payload["digest"] == digest_of(_note(lab))

    def test_the_replacement_is_one_history_commit(self, lab: Workspace) -> None:
        _fields(lab, "--set", '{"status": "active"}')
        log = subprocess.run(
            ["git", "-C", str(lab.root), "log", "--format=%B"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "knowledge.fields_replaced" in log

    def test_the_fields_can_come_from_a_file(self, lab: Workspace, tmp_path: Path) -> None:
        source = tmp_path / "fields.json"
        source.write_text('{"status": "retired"}', encoding="utf-8")
        assert _fields(lab, "--set", str(source)).exit_code == 0
        assert _note(lab).fields().status == "retired"

    @pytest.mark.parametrize(
        ("fields", "named"),
        [('{"status": "finished"}', "status"), ('{"verdict": "supported"}', "verdict")],
    )
    def test_a_value_or_key_the_class_refuses_writes_nothing(
        self, lab: Workspace, fields: str, named: str
    ) -> None:
        before = (Path(str(lab.root)) / DOC).read_bytes()
        result = _fields(lab, "--set", fields)
        assert result.exit_code == 1
        assert named in result.output
        assert (Path(str(lab.root)) / DOC).read_bytes() == before

    def test_a_stale_digest_writes_nothing(self, lab: Workspace) -> None:
        read = json.loads(_fields(lab).stdout)["digest"]
        assert _fields(lab, "--set", '{"status": "active"}', "--if-match", read).exit_code == 0

        result = _fields(lab, "--set", '{"status": "retired"}', "--if-match", read)
        assert result.exit_code == 1
        assert "changed since it was read" in " ".join(result.output.split())
        assert _note(lab).fields().status == "active"
