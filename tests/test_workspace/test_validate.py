"""Workspace conformance validation (``validate_workspace`` / ``Workspace.validate``).

The layout law is enforced by the writers; this checker holds a tree that was
assembled some *other* way — by hand, by an adoption tool, by an older molab —
to the same standard. The load-bearing property is that a workspace molab
itself just wrote must validate clean: a checker that flags its own writer is
worthless.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.workspace import Workspace
from molab.workspace.validate import validate_workspace


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

    def test_missing_workspace_json_is_not_a_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "bare").mkdir()
        report = validate_workspace(tmp_path / "bare")
        assert not report.ok
        assert [v.rule for v in report.errors] == ["workspace.entity"]

    def test_missing_directory_reports_rather_than_raises(self, tmp_path: Path) -> None:
        report = validate_workspace(tmp_path / "nope")
        assert not report.ok
        assert [v.rule for v in report.errors] == ["workspace.missing"]

    def test_missing_entity_file_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        (Path(ws.get_project("alpha").resolve()) / "project.json").unlink()

        report = ws.validate()
        assert "project.entity" in {v.rule for v in report.errors}

    def test_missing_concept_marker_is_an_error(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        proj = ws.get_project("alpha")
        entity = Path(proj.resolve()) / "project.json"
        payload = json.loads(entity.read_text())
        payload.pop("type", None)
        entity.write_text(json.dumps(payload))

        report = ws.validate()
        marker = [v for v in report.errors if v.rule == "concept.marker"]
        assert marker and marker[0].path == f"projects/{proj._name}"

    def test_workspace_type_on_entity_is_the_concept_marker(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        report = ws.validate()
        assert "concept.marker" not in {v.rule for v in report.errors}

    def test_stray_directory_is_flagged(self, tmp_path: Path) -> None:
        # A results dir dropped at the root is neither a container nor a Concept.
        ws = _workspace(tmp_path)
        (Path(ws.resolve()) / "leftover-run-output").mkdir()

        report = ws.validate()
        stray = [v for v in report.errors if v.rule == "layout.stray"]
        assert [v.path for v in stray] == ["leftover-run-output"]

    def test_a_concept_mounted_anywhere_is_not_a_stray(self, tmp_path: Path) -> None:
        # Any Folder subclass may mount at any Folder; the document's own head is
        # what makes it legitimate, not its name.
        from molab.knowledge import mount_note

        ws = _workspace(tmp_path)
        mount_note(ws.get_project("alpha"), "reading")

        report = ws.validate()
        assert "layout.stray" not in {v.rule for v in report.errors}
        assert report.ok

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
        (Path(ws.resolve()) / "leftover").mkdir()
        report = ws.validate()
        stray = next(v for v in report.errors if v.rule == "layout.stray")
        assert stray.hint
        assert "projects" in stray.hint or "meta.json" in stray.hint
        assert "layout.stray" in report.issues_by_rule()
        assert report.error_count >= 1
        assert report.ok is False
