"""Workspace conformance validation (``validate_workspace`` / ``Workspace.validate``).

The layout law is enforced by the writers; this checker holds a tree that was
assembled some *other* way — by hand, by an adoption tool, by an older molab —
to the same standard. The load-bearing property is that a workspace molab
itself just wrote must validate clean: a checker that flags its own writer is
worthless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.validate import HOST_LEVELS, classify_entry, validate_workspace
from tests.support.records import read_record, write_record


def _workspace(tmp_path: Path) -> Workspace:
    """A materialized workspace with one project/experiment/run."""
    ws = Workspace(root=tmp_path / "lab")
    ws.materialize()
    exp = ws.add_project("alpha").add_experiment("sweep")
    exp.add_run(params={"t": 1})
    return ws


class TestValidateWorkspace:
    def test_a_workspace_molab_wrote_conforms(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        report = ws.validate()
        assert report.ok, report.violations
        assert report.errors == ()
        assert validate_workspace(ws).ok

    def test_never_executed_run_conforms_without_ops_warning(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        report = ws.validate()
        assert "run.ops" not in {v.rule for v in report.warnings}
        assert not any("ops/run.json" in v.detail for v in report.violations)
        assert report.ok

    def test_missing_root_record_is_not_a_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "bare").mkdir()
        report = validate_workspace(tmp_path / "bare")
        assert not report.ok
        assert [v.rule for v in report.errors] == ["workspace.entity"]

    def test_missing_directory_reports_rather_than_raises(self, tmp_path: Path) -> None:
        report = validate_workspace(tmp_path / "nope")
        assert not report.ok
        assert [v.rule for v in report.errors] == ["workspace.missing"]

    def test_missing_record_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        (Path(ws.get_project("alpha").resolve()) / "index.md").unlink()

        report = ws.validate()
        assert "project.entity" in {v.rule for v in report.errors}

    def test_a_record_without_type_is_no_record(self, tmp_path: Path) -> None:
        """``concept.marker`` folded into ``{level}.entity``: no ``type``, no record."""
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        payload = read_record(proj.resolve())
        payload.pop("type", None)
        write_record(proj.resolve(), payload)

        report = ws.validate()
        missing = [v for v in report.errors if v.rule == "project.entity"]
        assert missing and missing[0].path == f"projects/{proj._name}"
        assert "concept.marker" not in {v.rule for v in report.violations}

    def test_a_canonical_zone_that_fails_its_model_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        payload = read_record(proj.resolve())
        payload.pop("id")
        write_record(proj.resolve(), payload)

        report = ws.validate()
        assert [v.path for v in report.errors if v.rule == "index.frontmatter"] == [
            f"projects/{proj._name}"
        ]

    def test_a_drifted_index_block_is_a_warning(self, tmp_path: Path) -> None:
        # D89: molab never reads the block, so drift misleads and breaks nothing.
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        write_record(proj.resolve(), read_record(proj.resolve()), index={"children": []})

        report = ws.validate()
        drift = [v for v in report.warnings if v.rule == "index.drift"]
        assert [v.path for v in drift] == [f"projects/{proj._name}"]
        assert "molab index sync" in drift[0].hint
        assert not [v for v in report.errors if v.rule == "index.drift"]

    def test_a_section_outside_the_reserved_keys_is_not_drift(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        ws.get_project("alpha").set_index_section("notes", [{"path": "knowledges/a.md"}])

        assert ws.validate().ok

    def test_a_leftover_legacy_record_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        (Path(proj.resolve()) / "project.json").write_text("{}")

        report = ws.validate()
        legacy = [v for v in report.errors if v.rule == "layout.legacy_record"]
        assert [v.path for v in legacy] == [f"projects/{proj._name}"]
        assert "molab migrate index" in legacy[0].hint

    def test_every_rule_has_a_hint(self) -> None:
        from molab.workspace.validate import _RULE_HINTS

        for rule in (
            "workspace.entity",
            "project.entity",
            "experiment.entity",
            "run.entity",
            "run.slug",
            "execution.name",
            "execution.id_mismatch",
            "index.frontmatter",
            "index.drift",
            "layout.legacy_record",
            "layout.stray",
            "scratch.stale",
        ):
            assert rule in _RULE_HINTS
            assert "`molab " in _RULE_HINTS[rule], rule
        assert "concept.marker" not in _RULE_HINTS

    def test_a_stray_at_every_level_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = Path(ws.resolve())
        (root / "leftover-run-output").mkdir()
        (root / "notes.txt").write_text("x")
        (root / "projects" / "alpha" / "plan").mkdir()
        (root / "projects" / "stray.json").write_text("{}")
        exp = root / "projects" / "alpha" / "experiments" / "sweep"
        (exp / "analysis.py").write_text("print(1)")
        (exp / "runs" / "README").write_text("x")
        run = next(exp.glob("runs/*/"))
        (run / "ops").mkdir()
        (run / "executions").mkdir()
        (run / "executions" / "list.txt").write_text("x")

        report = ws.validate()
        stray = sorted(v.path for v in report.errors if v.rule == "layout.stray")

        run_rel = run.relative_to(root).as_posix()
        assert stray == sorted(
            [
                "leftover-run-output",
                "notes.txt",
                "projects/alpha/plan",
                "projects/stray.json",
                "projects/alpha/experiments/sweep/analysis.py",
                "projects/alpha/experiments/sweep/runs/README",
                f"{run_rel}/ops",
                f"{run_rel}/executions/list.txt",
            ]
        )
        assert not report.ok

    def test_declared_names_are_legal(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = Path(ws.resolve())
        for name in ("AGENTS.md", "CLAUDE.md", ".gitignore"):
            (root / name).write_text("x")
        (root / ".claude").mkdir()
        (root / ".git").mkdir()
        exp = root / "projects" / "alpha" / "experiments" / "sweep"
        (exp / "workflow.py").write_text("x")
        (exp / "scratch" / "probe").mkdir(parents=True)
        (exp / "__pycache__").mkdir()
        from molab.workspace.index_projection import sync_index

        sync_index(ws)

        report = ws.validate()
        assert report.ok, report.violations
        assert report.warnings == ()

    def test_a_container_named_by_extra_is_legal_only_through_extra(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        run = next(Path(ws.resolve()).glob("projects/alpha/experiments/sweep/runs/*"))
        (run / "knowledges").mkdir()
        (Path(ws.resolve()) / "knowledges").mkdir()

        bare = validate_workspace(ws)
        assert {v.path.rsplit("/", 1)[-1] for v in bare.errors if v.rule == "layout.stray"} == {
            "knowledges"
        }
        extra = {level: frozenset({"knowledges"}) for level in HOST_LEVELS}
        assert validate_workspace(ws, extra=extra).ok

    def test_a_run_dir_not_named_after_its_params_is_a_warning(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        runs = Path(ws.resolve()) / "projects" / "alpha" / "experiments" / "sweep" / "runs"
        assert [v for v in ws.validate().violations if v.rule == "run.slug"] == []
        (runs / "t=1").rename(runs / "t=1-2")
        from molab.workspace.index_projection import sync_index

        sync_index(ws)
        assert [v for v in ws.validate().violations if v.rule == "run.slug"] == []

        (runs / "t=1-2").rename(runs / "renamed")
        sync_index(ws)
        report = ws.validate()
        slug = [v for v in report.violations if v.rule == "run.slug"]
        assert [(v.path.rsplit("/", 1)[-1], v.severity) for v in slug] == [("renamed", "warning")]
        assert "molab index sync" in slug[0].hint

    def test_an_attempt_dir_not_named_after_its_id_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        run = ws.get_project("alpha").get_experiment("sweep").list_runs()[0]
        with run.start():
            pass
        execs = Path(run.resolve()) / "executions"
        assert [v for v in ws.validate().violations if v.rule == "execution.id_mismatch"] == []

        (execs / "e01").rename(execs / "e07")
        report = ws.validate()
        mismatch = [v for v in report.errors if v.rule == "execution.id_mismatch"]
        assert [v.path.rsplit("/", 1)[-1] for v in mismatch] == ["e07"]
        assert "'e01'" in mismatch[0].detail

    def test_an_old_scratch_entry_is_a_warning(self, tmp_path: Path) -> None:
        import os
        import time

        ws = _workspace(tmp_path)
        scratch = Path(ws.resolve()) / "projects" / "alpha" / "experiments" / "sweep" / "scratch"
        (scratch / "fresh").mkdir(parents=True)
        old = scratch / "old.py"
        old.write_text("x")
        month_ago = time.time() - 30 * 86400
        os.utime(old, (month_ago, month_ago))

        report = ws.validate()
        stale = [v for v in report.violations if v.rule == "scratch.stale"]
        assert [(v.path.rsplit("/", 1)[-1], v.severity) for v in stale] == [("old.py", "warning")]
        assert "molab scratch clean" in stale[0].hint
        assert report.ok

    def test_a_scratch_flag_alone_out_of_date_is_a_warning(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        exp = Path(ws.resolve()) / "projects" / "alpha" / "experiments" / "sweep"
        (exp / "scratch").mkdir()

        drift = [v for v in ws.validate().violations if v.rule == "index.drift"]
        assert [(v.severity, v.detail) for v in drift] == [
            ("warning", "derived index keys differ: scratch")
        ]

    def test_classify_entry_is_pure_and_per_level(self) -> None:
        assert classify_entry("workspace", "projects", True) is None
        assert classify_entry("workspace", "projects", False) == "layout.stray"
        assert classify_entry("workspace", "index.md", False) is None
        assert classify_entry("project", "notes.md", False) == "layout.stray"
        assert classify_entry("experiment", "scratch", True) is None
        assert classify_entry("experiment", "workflow.py", False) is None
        assert classify_entry("run", "executions", True) is None
        assert classify_entry("runs", "anything", True) is None
        assert classify_entry("runs", "README", False) == "layout.stray"
        assert classify_entry("executions", "e03", True) is None
        assert (
            classify_entry("executions", "0190f0e2-7c1a-7d4e-9b2a-3c4d5e6f7a8b", True)
            == "execution.legacy_name"
        )
        assert classify_entry("executions", "attempt-1", True) == "execution.name"
        assert classify_entry("execution", "out", True) is None
        assert classify_entry("execution", "execution.json", False) is None
        assert classify_entry("execution", "notes.txt", False) == "layout.stray"
        assert classify_entry("project", "knowledges", True) == "layout.stray"
        assert (
            classify_entry(
                "project", "knowledges", True, extra={"project": frozenset({"knowledges"})}
            )
            is None
        )
        with pytest.raises(ValueError, match="unknown level"):
            classify_entry("nowhere", "x", True)

    def test_execution_dir_registered_after_import_is_not_a_stray(self, tmp_path: Path) -> None:
        from molab.workspace.execution_dirs import ExecutionDir, register_execution_dir

        register_execution_dir(
            ExecutionDir(
                name="late", purpose="registered after import", versioned=False, products=False
            )
        )
        ws = _workspace(tmp_path)
        run = next(Path(ws.resolve()).glob("projects/alpha/experiments/sweep/runs/*"))
        (run / "executions" / "e01" / "late").mkdir(parents=True)
        (run / "executions" / "e01" / "leftover").mkdir()

        report = ws.validate()
        stray = [item for item in report.errors if item.rule == "layout.stray"]

        assert not any(
            item.path.endswith("/late") or item.path.endswith("e01/late") for item in stray
        )
        assert len(stray) == 1
        assert stray[0].path.endswith("executions/e01/leftover")

    def test_legacy_uuid_attempt_dir_is_a_warning(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        run = next(Path(ws.resolve()).glob("projects/alpha/experiments/sweep/runs/*"))
        name = "0190f0e2-7c1a-7d4e-9b2a-3c4d5e6f7a8b"
        (run / "executions" / name).mkdir(parents=True)

        report = ws.validate()
        legacy = [item for item in report.violations if item.rule == "execution.legacy_name"]
        named = [item for item in report.violations if item.rule == "execution.name"]

        assert named == []
        assert len(legacy) == 1
        assert legacy[0].severity == "warning"
        assert "molab migrate layout" in legacy[0].detail
        assert "molab migrate layout" in legacy[0].hint
        assert report.ok is True

    def test_non_attempt_name_is_flagged(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        run = next(Path(ws.resolve()).glob("projects/alpha/experiments/sweep/runs/*"))
        (run / "executions" / "attempt-1").mkdir(parents=True)

        report = ws.validate()
        named = [item for item in report.errors if item.rule == "execution.name"]

        assert len(named) == 1
        assert "legacy attempt UUID" in named[0].detail

    def test_stray_inside_an_execution_dir_is_flagged(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = Path(ws.resolve())
        run = next(root.glob("projects/alpha/experiments/sweep/runs/*"))
        (run / "executions" / "e01" / "leftover").mkdir(parents=True)

        report = ws.validate()
        stray = [v for v in report.errors if v.rule == "layout.stray"]

        assert len(stray) == 1
        assert stray[0].path.endswith("executions/e01/leftover")

    def test_validate_takes_no_container_heads_keyword(self, tmp_path: Path) -> None:
        # The container-head check was deleted, not parameterized: no dead knob.
        ws = _workspace(tmp_path)
        with pytest.raises(TypeError):
            validate_workspace(ws.resolve(), container_heads=("finding.json",))  # type: ignore[call-arg]

    def test_project_dir_that_is_not_a_slug_is_flagged(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        projects = Path(ws.resolve()) / "projects"
        (projects / proj._name).rename(projects / "Not_A_Slug")

        report = ws.validate()
        assert "project.slug" in {v.rule for v in report.errors}

    def test_report_is_frozen_and_summarizes(self, tmp_path: Path) -> None:
        report = _workspace(tmp_path).validate()
        with pytest.raises(Exception):  # noqa: B017 — pydantic frozen guard
            report.root = "elsewhere"
        assert "conforms" in report.summary() or "warning" in report.summary()

    def test_report_to_dict_is_agent_tool_shaped(self, tmp_path: Path) -> None:
        # MCP validate_workspace / molab validate --json share this wire shape.
        report = _workspace(tmp_path).validate()
        payload = report.to_dict()
        assert payload["ok"] is True
        assert payload["error_count"] == 0
        assert payload["warning_count"] == 0
        assert "summary" in payload
        assert "next_actions" in payload
        assert payload["next_actions"] == []
        assert all(
            set(v) >= {"path", "rule", "detail", "severity", "hint"} for v in payload["violations"]
        )
        # Hints are non-empty so an agent can act without re-reading the law.
        assert all(v["hint"] for v in payload["violations"])

    def test_error_carries_rule_specific_hint(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = Path(ws.resolve())
        run = next(root.glob("projects/alpha/experiments/sweep/runs/*"))
        (run / "executions" / "e01" / "leftover").mkdir(parents=True)
        report = ws.validate()
        stray = next(v for v in report.errors if v.rule == "layout.stray")
        assert stray.hint
        assert "execution" in stray.hint
        assert "layout.stray" in report.issues_by_rule()
        assert report.error_count >= 1
        assert report.ok is False
