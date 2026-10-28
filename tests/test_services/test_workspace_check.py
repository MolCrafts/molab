"""``services.workspace_check`` — the one home of the rules agent hooks enforce (D91).

The harness hook only forwards; everything it decides comes from here. The
Verdict JSON is that contract, so its shape is pinned field by field.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from molab import frontmatter
from molab.knowledge import Note
from molab.knowledge.write import write_knowledge
from molab.services.workspace_check import (
    SNAPSHOT_TTL,
    Verdict,
    baseline_path,
    check_path,
    check_tree,
    check_workspace,
    snapshot,
    snapshot_name,
    write_baseline,
)
from molab.workspace import Workspace

VERDICT_KEYS = {"in_workspace", "allowed", "rule", "reason", "command", "path", "issues"}
ISSUE_KEYS = {"rule", "severity", "path", "hint"}


@pytest.fixture
def lab(tmp_path: Path) -> dict[str, Any]:
    """A workspace with one run that has a sealed attempt ``e01``."""
    ws = Workspace(tmp_path / "lab")
    ws.materialize()
    exp = ws.add_project("alpha").add_experiment("sweep")
    run = exp.add_run(params={"t": 1})
    with run.start():
        pass
    root = Path(str(ws.resolve()))
    return {
        "ws": ws,
        "root": root,
        "exp": root / "projects/alpha/experiments/sweep",
        "run": Path(str(run.resolve())),
        "attempt": Path(str(run.resolve())) / "executions" / "e01",
    }


def _verdict(path: Path, content: str | None = "x", op: str = "write") -> Verdict:
    return check_path(path, op, content)


def _deny(verdict: Verdict, rule: str) -> None:
    assert verdict.allowed is False, verdict
    assert verdict.in_workspace is True
    assert verdict.rule == rule
    assert verdict.reason
    assert verdict.command and verdict.command.startswith("molab ")


class TestVerdictShape:
    def test_the_json_carries_exactly_the_contract_fields(self, lab: dict[str, Any]) -> None:
        refused = _verdict(lab["exp"] / "analysis.py").model_dump(mode="json")
        assert set(refused) == VERDICT_KEYS
        assert isinstance(refused["in_workspace"], bool)
        assert isinstance(refused["allowed"], bool)
        assert isinstance(refused["rule"], str)
        assert isinstance(refused["reason"], str)
        assert isinstance(refused["command"], str)
        assert refused["path"] == "projects/alpha/experiments/sweep/analysis.py"
        assert refused["issues"] == []

        (lab["exp"] / "stray.txt").write_text("x")
        tree = check_tree(lab["root"]).model_dump(mode="json")
        assert set(tree) == VERDICT_KEYS
        assert tree["allowed"] is False
        assert tree["issues"]
        assert all(set(issue) == ISSUE_KEYS for issue in tree["issues"])

    def test_outside_a_workspace_everything_is_allowed(self, tmp_path: Path) -> None:
        verdict = _verdict(tmp_path / "anything.json")
        assert (verdict.in_workspace, verdict.allowed, verdict.rule) == (False, True, None)
        tree = check_tree(tmp_path)
        assert (tree.in_workspace, tree.allowed) == (False, True)


class TestCheckPathDeny:
    def test_machine_state(self, lab: dict[str, Any]) -> None:
        _deny(_verdict(lab["root"] / ".molab" / "locks" / "x"), "path.machine")
        _deny(_verdict(lab["root"] / ".git" / "config"), "path.machine")

    def test_a_record_frontmatter_change(self, lab: dict[str, Any]) -> None:
        index = lab["run"] / "index.md"
        meta, body = frontmatter.split(index.read_text())
        meta["parameters"] = {"t": 2}
        _deny(_verdict(index, frontmatter.dump(meta, body), "edit"), "index.frontmatter")

        meta, body = frontmatter.split(index.read_text())
        meta["index"] = {"parent": "../../index.md"}
        verdict = _verdict(index, frontmatter.dump(meta, body), "edit")
        _deny(verdict, "index.frontmatter")
        assert verdict.command == "molab index write -p alpha -e sweep --run t=1 --from FILE"

    def test_an_unknown_record_change_is_refused(self, lab: dict[str, Any]) -> None:
        _deny(_verdict(lab["exp"] / "index.md", None, "edit"), "index.frontmatter")

    def test_a_new_record(self, lab: dict[str, Any]) -> None:
        verdict = _verdict(lab["root"] / "projects" / "beta" / "index.md", "# Beta\n")
        _deny(verdict, "index.create")
        assert verdict.command == "molab project create NAME"
        run_verdict = _verdict(lab["exp"] / "runs" / "new" / "index.md", "---\ntype: x\n---\n")
        _deny(run_verdict, "index.create")
        assert run_verdict.command.startswith("molab runs create alpha sweep")

    @pytest.mark.parametrize(
        "rel",
        ["assets/data/asset.json", "assets/data/versions/v001.json", "assets/data/blob.bin"],
    )
    def test_the_asset_store(self, lab: dict[str, Any], rel: str) -> None:
        verdict = _verdict(lab["root"] / "projects/alpha" / rel, "{}")
        _deny(verdict, "asset.owned")
        assert verdict.command == "molab asset import NAME SRC --project alpha"

    def test_a_legacy_record_file(self, lab: dict[str, Any]) -> None:
        verdict = _verdict(lab["run"] / "run.json", "{}")
        _deny(verdict, "layout.legacy_record")
        assert "run.json is not a file in molab" in verdict.reason
        assert verdict.command.startswith("molab runs create")
        _deny(_verdict(lab["exp"] / "meta.json", "{}"), "layout.legacy_record")
        _deny(_verdict(lab["root"] / "projects/alpha/project.json", "{}"), "layout.legacy_record")

    @pytest.mark.parametrize(
        "rel",
        [
            "execution.json",
            "workflow.json",
            "alive",
            "run.log",
            "traceback.txt",
            "source/workflow.py",
            "artifacts/fit.png",
            "jobs/slurm-1.out",
            "checkpoints/c1.pt",
        ],
    )
    def test_what_an_attempt_owns(self, lab: dict[str, Any], rel: str) -> None:
        verdict = _verdict(lab["attempt"] / rel)
        _deny(verdict, "execution.owned")
        assert "molab runs adopt" in verdict.command

    def test_a_new_attempt_by_hand(self, lab: dict[str, Any]) -> None:
        _deny(_verdict(lab["run"] / "executions" / "e02" / "out" / "x.dat"), "execution.owned")

    def test_a_knowledge_document_without_a_known_class(self, lab: dict[str, Any]) -> None:
        doc = lab["exp"] / "knowledges" / "idea.md"
        _deny(_verdict(doc, "# no class\n"), "knowledge.class")
        _deny(_verdict(doc, "---\nclass: Essay\n---\nx\n"), "knowledge.class")
        verdict = _verdict(doc, "# no class\n")
        assert "--class" in verdict.command
        _deny(_verdict(lab["exp"] / "knowledges" / "data.csv"), "knowledge.stray")

    def test_a_new_stray(self, lab: dict[str, Any]) -> None:
        verdict = _verdict(lab["exp"] / "analysis.py")
        _deny(verdict, "layout.stray")
        assert "projects/alpha/experiments/sweep/scratch/" in verdict.reason
        assert "molab runs adopt" in verdict.reason
        _deny(_verdict(lab["root"] / "notes" / "todo.md"), "layout.stray")
        _deny(_verdict(lab["run"] / "plot.png"), "layout.stray")
        _deny(_verdict(lab["attempt"] / "notes.txt"), "layout.stray")


class TestCheckPathAllow:
    @pytest.mark.parametrize(
        "rel",
        [
            "projects/alpha/experiments/sweep/scratch/probe.py",
            "projects/alpha/experiments/sweep/scratch/x/run.json",
            "projects/alpha/experiments/sweep/scratch/y/meta.json",
            "projects/alpha/experiments/sweep/workflow.py",
            "AGENTS.md",
            "CLAUDE.md",
            ".gitignore",
            ".claude/settings.json",
        ],
    )
    def test_places_an_agent_may_write(self, lab: dict[str, Any], rel: str) -> None:
        verdict = _verdict(lab["root"] / rel)
        assert verdict.allowed, verdict
        assert verdict.rule is None

    @pytest.mark.parametrize(
        "rel", ["out/nve/meta.json", "out/nve/run.json", "out/nve/log.lammps", "work/tmp.txt"]
    )
    def test_a_task_tier_of_an_attempt(self, lab: dict[str, Any], rel: str) -> None:
        # A solver's own meta.json / run.json is science payload, not a record.
        assert _verdict(lab["attempt"] / rel).allowed

    def test_a_body_only_change_of_a_record(self, lab: dict[str, Any]) -> None:
        index = lab["exp"] / "index.md"
        meta, body = frontmatter.split(index.read_text())
        assert _verdict(index, frontmatter.dump(meta, body + "\nMore notes.\n"), "edit").allowed

    def test_an_existing_stray_is_old_debt(self, lab: dict[str, Any]) -> None:
        old = lab["exp"] / "analysis.py"
        old.write_text("print(1)\n")
        assert _verdict(old, "print(2)\n", "edit").allowed
        # …but a new file inside an old stray directory is a new stray.
        (lab["exp"] / "old-dir").mkdir()
        assert not _verdict(lab["exp"] / "old-dir" / "new.py").allowed

    def test_a_knowledge_document_with_a_class(self, lab: dict[str, Any]) -> None:
        doc = lab["exp"] / "knowledges" / "idea.md"
        assert _verdict(doc, "---\nclass: Note\n---\n# Idea\n").allowed

    def test_an_invalid_op_is_refused(self, lab: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="op must be"):
            check_path(lab["root"] / "x", "delete", None)


class TestSnapshots:
    def test_since_reports_only_errors_added_after_the_snapshot(self, lab: dict[str, Any]) -> None:
        (lab["exp"] / "old.txt").write_text("debt")
        taken = check_tree(lab["root"], snapshot="session-1")
        assert taken.allowed and taken.path == ".molab/check/session-1.json"

        assert check_tree(lab["root"], since="session-1").allowed
        (lab["exp"] / "new.txt").write_text("fresh")

        verdict = check_tree(lab["root"], since="session-1")

        assert verdict.allowed is False
        assert [(i.rule, i.path) for i in verdict.issues] == [
            ("layout.stray", "projects/alpha/experiments/sweep/new.txt")
        ]
        assert verdict.rule == "layout.stray"

    def test_a_missing_snapshot_falls_back_to_the_baseline(self, lab: dict[str, Any]) -> None:
        ws = lab["ws"]
        (lab["exp"] / "old.txt").write_text("debt")
        verdict = check_tree(lab["root"], since="never-taken")
        assert verdict.allowed
        assert verdict.reason == "no snapshot; cannot tell what is new"

        write_baseline(ws)
        assert check_tree(lab["root"], since="never-taken").allowed
        (lab["exp"] / "new.txt").write_text("fresh")
        fallback = check_tree(lab["root"], since="never-taken")
        assert not fallback.allowed
        assert "baseline" in fallback.reason
        assert not check_tree(lab["root"], new_only=True).allowed

    def test_new_only_without_a_baseline_cannot_tell(self, lab: dict[str, Any]) -> None:
        (lab["exp"] / "old.txt").write_text("debt")
        assert not baseline_path(lab["ws"]).exists()
        verdict = check_tree(lab["root"], new_only=True)
        assert verdict.allowed
        assert verdict.reason == "no snapshot; cannot tell what is new"

    def test_names_are_sanitized(self, lab: dict[str, Any]) -> None:
        assert snapshot_name("../../etc/passwd") == "______etc_passwd"
        assert snapshot_name("") == "default"
        written = snapshot(lab["ws"], "a/b c")
        assert written.name == "a_b_c.json"
        assert written.parent == lab["root"] / ".molab" / "check"

    def test_old_snapshots_are_dropped_on_write(self, lab: dict[str, Any]) -> None:
        old = snapshot(lab["ws"], "old")
        stamp = time.time() - SNAPSHOT_TTL.total_seconds() - 86400
        os.utime(old, (stamp, stamp))
        recent = snapshot(lab["ws"], "recent")

        assert not old.exists()
        assert recent.exists()
        data = json.loads(recent.read_text())
        assert data["errors"] == []


class TestCheckWorkspace:
    def test_knowledge_is_legal_and_its_issues_fold_in(self, lab: dict[str, Any]) -> None:
        ws = lab["ws"]
        write_knowledge(ws, name="n", of=Note, created_by="t", text="x")
        assert check_workspace(ws).ok, check_workspace(ws).violations

        (lab["root"] / "knowledges" / "bare.md").write_text("no class\n")
        rules = {(v.rule, v.path) for v in check_workspace(ws).errors}
        assert ("knowledge.class", "knowledges/bare.md") in rules
        assert not any(rule == "layout.stray" for rule, _ in rules)

    def test_the_report_keeps_the_validate_json_keys(self, lab: dict[str, Any]) -> None:
        payload = check_workspace(lab["ws"]).to_dict()
        assert {
            "ok",
            "root",
            "summary",
            "error_count",
            "warning_count",
            "violations",
            "next_actions",
        } <= set(payload)
