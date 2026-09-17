"""Workspace history is git (``molab.workspace.history``).

Two properties matter and are locked here:

1. **It is real git.** A fact is a commit over the files it describes, with
   the typed fields in the message trailers, so ``git log`` — not a molab
   reader — is the provenance query, and ``git push`` is the backup.
2. **It is a soft dependency.** Nothing in molab reads history to answer an
   operational question, so a workspace with no git still runs science and
   simply records less.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from molab.workspace import Workspace
from molab.workspace.history import (
    SYSTEM_AGENT,
    EntityRef,
    GitHistory,
    Relation,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

RUN = EntityRef(id="01a06e0a-6a31-793c-bbfb-a82d0038406a", type="run")
EXECUTION = EntityRef(id="01a06e0a-6a31-793c-bbfb-a82d0038406a:e01", type="execution")


def _git(root, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


class TestInit:
    def test_init_is_idempotent_and_writes_an_ignore_file(self, tmp_path):
        history = GitHistory(tmp_path)
        assert not history.enabled()
        assert history.init()
        assert history.init()
        assert history.enabled()
        assert ".molab/" in (tmp_path / ".gitignore").read_text()

    def test_a_workspace_without_git_still_records_nothing_rather_than_failing(self, tmp_path):
        history = GitHistory(tmp_path)
        assert history.record("RunDefined", subject=RUN) is None
        assert history.entries() == []


class TestRecord:
    def test_a_fact_is_a_commit_over_the_files_it_describes(self, tmp_path):
        history = GitHistory(tmp_path)
        history.init()
        (tmp_path / "run.json").write_text('{"id": "x"}')

        commit = history.record(
            "RunDefined",
            subject=RUN,
            summary="dp=5_seed=42",
            paths=(tmp_path / "run.json",),
        )

        assert commit is not None
        assert "run.json" in _git(tmp_path, "show", "--name-only", "--format=", commit)
        assert _git(tmp_path, "log", "-1", "--format=%s").strip() == "RunDefined: dp=5_seed=42"

    def test_nothing_to_commit_records_nothing(self, tmp_path):
        history = GitHistory(tmp_path)
        history.init()
        history.sweep()
        assert history.record("RunDefined", subject=RUN) is None

    def test_typed_fields_survive_the_round_trip(self, tmp_path):
        history = GitHistory(tmp_path)
        history.init()
        (tmp_path / "execution.json").write_text("{}")
        history.record(
            "ExecutionSealed",
            subject=EXECUTION,
            agent=SYSTEM_AGENT,
            relations=(Relation(predicate="realizationOf", object=RUN),),
            summary="dp=5_seed=42 e01 succeeded",
        )

        entry = history.entries(limit=1)[0]
        assert entry.event == "ExecutionSealed"
        assert entry.subject == EXECUTION
        assert entry.agent == SYSTEM_AGENT
        assert entry.relations[0].predicate == "realizationOf"
        assert entry.relations[0].object == RUN
        assert entry.summary == "dp=5_seed=42 e01 succeeded"


class TestQuery:
    def test_an_entity_is_found_through_a_relation_not_only_as_subject(self, tmp_path):
        history = GitHistory(tmp_path)
        history.init()
        for index in range(2):
            (tmp_path / f"f{index}.json").write_text("{}")
            history.record(
                "ExecutionSealed",
                subject=EntityRef(id=f"{RUN.id}:e0{index + 1}", type="execution"),
                relations=(Relation(predicate="realizationOf", object=RUN),),
            )
        (tmp_path / "other.json").write_text("{}")
        history.record("RunDefined", subject=EntityRef(id="other-run", type="run"))

        found = history.entries(entity_id=RUN.id)
        assert len(found) == 2
        assert all(item.mentions(RUN.id) for item in found)

    def test_event_filter_narrows_and_newest_comes_first(self, tmp_path):
        history = GitHistory(tmp_path)
        history.init()
        for index, event in enumerate(("ExecutionCreated", "ExecutionStarted", "ExecutionSealed")):
            (tmp_path / f"f{index}.json").write_text("{}")
            history.record(event, subject=EXECUTION, summary=str(index))

        assert next(item.event for item in history.entries()) == "ExecutionSealed"
        sealed = history.entries(event="ExecutionSealed")
        assert [item.event for item in sealed] == ["ExecutionSealed"]


class TestSoftDependency:
    def test_science_runs_and_is_readable_with_no_history_at_all(self, tmp_path):
        """No `git init`: the workspace still records everything that matters."""
        ws = Workspace(tmp_path / "lab", name="lab")
        run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        with run.start() as ctx:
            ctx.emit_artifact({"loss": 0.1}, name="metrics.json")

        assert not (tmp_path / "lab" / ".git").exists()
        execution = run.executions[-1]
        assert execution.status.value == "succeeded"
        assert execution.sealed
        assert [a.name for a in execution.artifacts] == ["metrics.json"]

    def test_history_added_later_captures_the_existing_tree(self, tmp_path):
        ws = Workspace(tmp_path / "lab", name="lab")
        ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})

        history = GitHistory(ws.root)
        history.init()
        assert history.sweep("adopt existing workspace") is not None
        tracked = _git(ws.root, "ls-files")
        assert "projects/p/experiments/e/runs/seed=1/run.json" in tracked
