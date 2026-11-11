"""The CLI paths an agent is given (D90 / D91).

``runs adopt`` records a job that ran outside molab; ``index show|write``
reads a record and writes its body; ``scratch clean`` empties old scratch;
``agents sync`` writes the guide; ``check path|command|tree`` answer the hooks with
the JSON the harness reads.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, ClassVar

import pytest
from typer.testing import CliRunner

from molab import frontmatter
from molab.cli import app
from molab.workspace import Workspace

runner = CliRunner()


def _invoke(*args: str, stdin: str | None = None) -> Any:
    result = runner.invoke(app, list(args), input=stdin)
    assert result.exit_code == 0, result.output
    return result


@pytest.fixture
def lab(tmp_path: Path) -> Path:
    ws = Workspace(tmp_path / "lab")
    ws.materialize()
    ws.add_project("alpha").add_experiment("sweep").add_run(params={"t": 1})
    return Path(str(ws.resolve()))


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """Files a hand-launched job left behind."""
    out = tmp_path / "job"
    (out / "nve").mkdir(parents=True)
    (out / "nve" / "traj.dat").write_text("frames")
    (out / "slurm-42.out").write_text("done")
    (out / "md.log").write_text("step 1")
    (out / "md.py").write_text("print('md')\n")
    return out


class TestRunsAdopt:
    def test_round_trip_seals_e01_with_source_and_validates_clean(
        self, lab: Path, job: Path
    ) -> None:
        result = _invoke(
            "runs", "adopt", "alpha", "sweep", "t=1",
            "--product", f"nve={job / 'nve'}",
            "--job", str(job / "slurm-42.out"),
            "--log", str(job / "md.log"),
            "--source", str(job / "md.py"),
            "--job-id", "42",
            "--created-by", "software:claude",
            "--json",
            "-ws", str(lab),
        )  # fmt: skip

        payload = json.loads(result.stdout)
        assert payload["execution_id"] == "e01"
        assert payload["status"] == "succeeded"
        assert payload["run_created"] is False
        attempt = lab / payload["path"]
        assert (attempt / "out" / "nve" / "traj.dat").read_text() == "frames"
        assert (attempt / "jobs" / "slurm-42.out").exists()
        assert (attempt / "run.log").read_text() == "step 1"
        assert (attempt / "source" / "md.py").exists()
        record = json.loads((attempt / "execution.json").read_text())
        assert record["sealed_at"]
        assert record["executor"]["job_ids"] == ["42"]
        assert record["created_by"] == {"id": "claude", "type": "software", "name": "claude"}
        assert not (job / "md.py").exists()

        validate = runner.invoke(app, ["validate", "-ws", str(lab)])
        assert validate.exit_code == 0, validate.output
        assert "conforms" in validate.output

    def test_params_create_the_run_first(self, lab: Path, job: Path) -> None:
        result = _invoke(
            "runs", "adopt", "alpha", "sweep", "t=9",
            "--params", '{"t": 9}',
            "--log", str(job / "md.log"),
            "--started", "2026-10-01T10:00:00+00:00",
            "--finished", "2026-10-01T12:00:00+00:00",
            "--status", "failed",
            "--json",
            "-ws", str(lab),
        )  # fmt: skip

        payload = json.loads(result.stdout)
        assert payload["run_created"] is True
        assert payload["run"] == "projects/alpha/experiments/sweep/runs/t=9"
        assert payload["status"] == "failed"
        assert payload["started_at"].startswith("2026-10-01T10:00:00")

    def test_an_unknown_run_without_params_is_refused(self, lab: Path, job: Path) -> None:
        result = runner.invoke(
            app,
            [
                "runs",
                "adopt",
                "alpha",
                "sweep",
                "nope",
                "--log",
                str(job / "md.log"),
                "-ws",
                str(lab),
            ],
        )
        assert result.exit_code == 1
        assert "--params" in result.output
        assert (job / "md.log").exists()


class TestIndexShowWrite:
    def test_write_replaces_the_body_and_keeps_the_frontmatter(self, lab: Path) -> None:
        index = lab / "projects" / "alpha" / "experiments" / "sweep" / "index.md"
        meta_before, _ = frontmatter.split(index.read_text())

        _invoke(
            "index", "write", "-p", "alpha", "-e", "sweep", "--from", "-", "-ws", str(lab),
            stdin="# Sweep\n\nWhy we ran it.\n",
        )  # fmt: skip

        meta_after, body = frontmatter.split(index.read_text())
        assert meta_after == meta_before
        assert body == "# Sweep\n\nWhy we ran it.\n"
        shown = _invoke("index", "show", "-p", "alpha", "-e", "sweep", "--body", "-ws", str(lab))
        assert shown.stdout == "# Sweep\n\nWhy we ran it.\n"
        head = _invoke(
            "index", "show", "-p", "alpha", "-e", "sweep", "--frontmatter", "-ws", str(lab)
        )
        assert frontmatter.split(head.stdout)[0] == meta_before
        assert "Why we ran it" not in head.stdout

    def test_write_refuses_text_whose_frontmatter_differs(self, lab: Path, tmp_path: Path) -> None:
        index = lab / "index.md"
        meta, _ = frontmatter.split(index.read_text())
        meta["name"] = "renamed"
        source = tmp_path / "new.md"
        source.write_text(frontmatter.dump(meta, "body\n"))
        before = index.read_text()

        result = runner.invoke(app, ["index", "write", "--from", str(source), "-ws", str(lab)])

        assert result.exit_code == 1
        assert index.read_text() == before

    def test_show_with_no_flags_is_the_root(self, lab: Path) -> None:
        shown = _invoke("index", "show", "-ws", str(lab))
        assert shown.stdout == (lab / "index.md").read_text()

    def test_sync_rebuilds_the_knowledge_sections(self, lab: Path) -> None:
        container = lab / "knowledges"
        container.mkdir()
        (container / "hand.md").write_text("---\nclass: Note\n---\n# Hand\n")

        result = _invoke("index", "sync", "-ws", str(lab))

        assert "1 knowledge section(s)" in " ".join(result.output.split())
        meta, _ = frontmatter.split((lab / "index.md").read_text())
        assert meta["index"]["knowledges"] == [
            {"path": "knowledges/hand.md", "class": "Note", "title": "Hand"}
        ]


class TestScratchClean:
    def test_dry_run_writes_nothing(self, lab: Path) -> None:
        scratch = lab / "projects" / "alpha" / "experiments" / "sweep" / "scratch"
        scratch.mkdir()
        old = scratch / "probe.py"
        old.write_text("x")
        stamp = time.time() - 10 * 86400
        os.utime(old, (stamp, stamp))
        before = sorted(str(p) for p in lab.rglob("*"))

        result = _invoke("scratch", "clean", "--older-than", "7d", "--dry-run", "-ws", str(lab))

        assert "probe.py" in result.output
        assert sorted(str(p) for p in lab.rglob("*")) == before

        _invoke("scratch", "clean", "--older-than", "7d", "-p", "alpha", "-ws", str(lab))
        assert not old.exists()

    def test_a_bad_duration_is_a_usage_error(self, lab: Path) -> None:
        result = runner.invoke(app, ["scratch", "clean", "--older-than", "soon", "-ws", str(lab)])
        assert result.exit_code == 2


class TestAgentsSync:
    def test_agents_sync_is_idempotent_and_keeps_outside_content(self, lab: Path) -> None:
        (lab / "AGENTS.md").write_text("# House rules\n")
        _invoke("agents", "sync", "-ws", str(lab))
        first = (lab / "AGENTS.md").read_text()
        second = _invoke("agents", "sync", "-ws", str(lab))

        assert first.startswith("# House rules\n")
        assert "<!-- molab:begin -->" in first
        assert "up to date" in " ".join(second.output.split())
        assert (lab / "AGENTS.md").read_text() == first
        assert "@AGENTS.md" in (lab / "CLAUDE.md").read_text()

    def test_init_runs_agents_sync_last(self, tmp_path: Path) -> None:
        _invoke("init", str(tmp_path / "fresh"))
        root = tmp_path / "fresh"
        assert "<!-- molab:end -->" in (root / "AGENTS.md").read_text()
        assert (root / ".molab" / "validate-baseline.json").exists()
        assert "**/experiments/*/scratch/" in (root / ".gitignore").read_text()


class TestCheckJson:
    """The JSON the harness hook parses (``molab_guard.py``)."""

    KEYS: ClassVar[set[str]] = {
        "in_workspace",
        "allowed",
        "rule",
        "reason",
        "command",
        "path",
        "root",
        "issues",
    }

    def test_check_path_refusal_matches_the_hook_fixture(self, lab: Path, tmp_path: Path) -> None:
        content = tmp_path / "content"
        content.write_text("{}")
        target = lab / "projects" / "alpha" / "experiments" / "sweep" / "runs" / "t=1" / "run.json"

        result = _invoke(
            "check", "path", str(target), "--op", "write",
            "--content-file", str(content), "--json",
        )  # fmt: skip

        verdict = json.loads(result.stdout)
        assert set(verdict) == self.KEYS
        assert verdict["root"] == os.path.realpath(lab)
        assert verdict["allowed"] is False
        assert verdict["rule"] == "layout.legacy_record"
        assert "run.json is not a file in molab" in verdict["reason"]
        assert verdict["command"].startswith("molab runs create alpha sweep --params")

    def test_check_path_allows_with_exit_zero(self, lab: Path) -> None:
        target = lab / "projects" / "alpha" / "experiments" / "sweep" / "scratch" / "t.py"
        verdict = json.loads(_invoke("check", "path", str(target), "--json").stdout)
        assert verdict["allowed"] is True
        assert verdict["root"] == os.path.realpath(lab)
        outside = json.loads(_invoke("check", "path", "/nonexistent/x", "--json").stdout)
        assert outside["in_workspace"] is False and outside["allowed"] is True
        assert outside["root"] is None

    def test_check_command_refusal_and_an_unparsed_allow(self, lab: Path, tmp_path: Path) -> None:
        target = lab / "projects" / "alpha" / "experiments" / "sweep" / "plot.py"
        refused = json.loads(
            _invoke(
                "check",
                "command",
                "--command",
                f"mv /tmp/a.py {target}",
                "--cwd",
                str(lab),
                "--json",
            ).stdout
        )
        assert set(refused) == self.KEYS
        assert refused["allowed"] is False
        assert refused["rule"] == "layout.stray"
        assert refused["root"] == os.path.realpath(lab)
        allowed = json.loads(
            _invoke(
                "check",
                "command",
                "--command",
                "mv 'unterminated",
                "--cwd",
                str(tmp_path),
                "--json",
            ).stdout
        )
        assert allowed["allowed"] is True
        assert allowed["in_workspace"] is False

    def test_check_tree_snapshot_then_since(self, lab: Path) -> None:
        taken = json.loads(_invoke("check", "tree", str(lab), "--snapshot", "s1", "--json").stdout)
        assert set(taken) == self.KEYS and taken["allowed"] is True
        assert taken["root"] == os.path.realpath(lab)

        (lab / "projects" / "alpha" / "x.py").write_text("x")
        since = json.loads(_invoke("check", "tree", str(lab), "--since", "s1", "--json").stdout)

        assert since["allowed"] is False
        assert [(i["rule"], i["path"]) for i in since["issues"]] == [
            ("layout.stray", "projects/alpha/x.py")
        ]
        assert all(set(i) == {"rule", "severity", "path", "hint"} for i in since["issues"])

    def test_check_tree_takes_one_mode(self, lab: Path) -> None:
        result = runner.invoke(
            app, ["check", "tree", str(lab), "--snapshot", "a", "--since", "b", "--json"]
        )
        assert result.exit_code == 2


class TestValidateBaseline:
    def test_new_only_reports_what_the_baseline_lacks(self, lab: Path) -> None:
        (lab / "projects" / "alpha" / "old.txt").write_text("debt")
        before = runner.invoke(app, ["validate", "--json", "-ws", str(lab)])
        assert before.exit_code == 1
        _invoke("validate", "--update-baseline", "--new-only", "--json", "-ws", str(lab))

        (lab / "projects" / "alpha" / "new.txt").write_text("fresh")
        result = runner.invoke(app, ["validate", "--new-only", "--json", "-ws", str(lab)])

        report = json.loads(result.stdout)
        assert result.exit_code == 1
        assert [v["path"] for v in report["violations"]] == ["projects/alpha/new.txt"]


class TestKnowledgeCreatedBy:
    def test_created_by_is_recorded(self, lab: Path) -> None:
        _invoke(
            "knowledge", "write", "Idea", "# An idea",
            "--on", "projects/alpha/experiments/sweep",
            "--class", "Finding",
            "--created-by", "claude",
            "--path", str(lab),
        )  # fmt: skip

        doc = lab / "projects" / "alpha" / "experiments" / "sweep" / "knowledges" / "idea.md"
        meta, _ = frontmatter.split(doc.read_text())
        assert meta["created_by"] == "claude"
        assert meta["class"] == "Finding"
        exp_meta, _ = frontmatter.split(doc.parent.parent.joinpath("index.md").read_text())
        assert exp_meta["index"]["knowledges"][0]["path"] == "knowledges/idea.md"
