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
from molab.workspace.validate import validate_workspace
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

    def test_a_drifted_index_block_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        write_record(proj.resolve(), read_record(proj.resolve()), index={"children": []})

        report = ws.validate()
        drift = [v for v in report.errors if v.rule == "index.drift"]
        assert [v.path for v in drift] == [f"projects/{proj._name}"]
        assert "molab index sync" in drift[0].hint

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
            "index.frontmatter",
            "index.drift",
            "layout.legacy_record",
        ):
            assert rule in _RULE_HINTS
        assert "concept.marker" not in _RULE_HINTS

    def test_unknown_host_directory_is_not_judged(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        root = Path(ws.resolve())
        (root / "leftover-run-output").mkdir()
        (root / "projects" / "alpha" / "plan").mkdir()
        run = next(root.glob("projects/alpha/experiments/sweep/runs/*"))
        (run / "knowledges").mkdir()
        (run / "ops").mkdir()

        report = ws.validate()

        assert report.ok, report.violations
        assert not any(v.rule == "layout.stray" for v in report.violations)

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
