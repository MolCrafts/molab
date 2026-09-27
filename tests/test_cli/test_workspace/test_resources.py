"""CLI run commands: harvest / analyze-failure gates and the run readers."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

from molab.cli import app
from molab.cli.workspace import resources
from molab.knowledge import Finding
from molab.profile import ProfileConfig
from molab.workspace import Workspace
from molab.workspace.run import Run


def _failed_run(tmp_path: Path):
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"x": 1}, id="aabbccdd")
    with run.start() as ctx:
        ctx.mark_failed("oom")
    return ws, exp, run


class TestRunHarvest:
    def test_of_gate_is_finding_observation_report(self) -> None:
        src = inspect.getsource(resources.run_harvest)
        assert '{"Finding": Finding, "Observation": Observation, "Report": Report}' in src
        assert "--of" in src
        assert "Finding, Observation, or Report" in src

    def test_rejected_kinds_exit_1(self, tmp_path: Path) -> None:
        ws, exp, run = _failed_run(tmp_path)
        runner = CliRunner()
        for kind in ("Decision", "Plan", "Note", "Literature", "FailureAnalysis"):
            result = runner.invoke(
                resources.run_app,
                [
                    "harvest",
                    exp.project.id,
                    exp.id,
                    run.id,
                    "narrative body",
                    "--of",
                    kind,
                    "--workspace",
                    str(ws.root),
                ],
            )
            # TargetOption may be named differently; fall back to cwd invoke.
            if result.exit_code not in {0, 1, 2}:
                pass
            if result.exit_code == 2:
                result = runner.invoke(
                    resources.run_app,
                    [
                        "harvest",
                        exp.project.id,
                        exp.id,
                        run.id,
                        "narrative body",
                        "--of",
                        kind,
                    ],
                    cwd=str(ws.root),
                )
            assert result.exit_code == 1, (kind, result.exit_code, result.output)


class TestRunHarvestRedirect:
    """07: the CLI harvests through ``molab.knowledge.harvest.harvest_run``.

    ``Run.harvest`` is what the CLI used to borrow; 08 deleted the workspace
    method, so the redirect must pass the real ``Run``, the class, the narrative
    and ``created_by`` straight through to the knowledge verb.
    """

    def test_calls_the_knowledge_verb_with_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, exp, run = _failed_run(tmp_path)
        import molab.knowledge.harvest as harvest_mod

        calls: list[dict[str, Any]] = []

        def probe(target: Any, of: Any, **kwargs: Any) -> Any:
            calls.append({"target": target, "of": of, **kwargs})
            return SimpleNamespace(name="probe")

        # 08 deleted the workspace verb; nothing on the Run can answer it now.
        assert not hasattr(Run, "harvest")
        monkeypatch.setattr(harvest_mod, "harvest_run", probe)

        result = CliRunner().invoke(
            resources.run_app,
            [
                "harvest",
                exp.project.id,
                exp.id,
                run.id,
                "the narrative",
                "--of",
                "Finding",
                "--workspace",
                str(ws.root),
            ],
        )

        assert result.exit_code == 0, result.output
        assert len(calls) == 1
        call = calls[0]
        assert isinstance(call["target"], Run)
        assert call["target"].id == run.id
        assert call["of"] is Finding
        assert call["narrative"] == "the narrative"
        assert call["created_by"] == "cli"

    def test_rejected_kind_never_calls_the_verb(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, exp, run = _failed_run(tmp_path)
        import molab.knowledge.harvest as harvest_mod

        calls: list[Any] = []

        def probe(*args: Any, **_kwargs: Any) -> Any:
            calls.append(args)
            return SimpleNamespace(name="probe")

        monkeypatch.setattr(harvest_mod, "harvest_run", probe)

        result = CliRunner().invoke(
            resources.run_app,
            [
                "harvest",
                exp.project.id,
                exp.id,
                run.id,
                "narrative body",
                "--of",
                "Decision",
                "--workspace",
                str(ws.root),
            ],
        )

        assert result.exit_code == 1, result.output
        assert calls == []


class TestRunAnalyzeFailure:
    def test_prints_report(self) -> None:
        src = inspect.getsource(resources.run_analyze_failure)
        assert "Report:" in src
        assert "FailureAnalysis" not in src


# ----------------------------------------------------------------------
# Run readers read the latest Execution (spec arch-own-02e-readers)

# Independent of ProfileConfig: sha256 over ``json.dumps({"nodes": 2},
# sort_keys=True)`` (default separators ``", "`` / ``": "``).
EXPECTED_HASH = hashlib.sha256(b'{"nodes": 2}').hexdigest()

_RUN_LEVEL_PROVENANCE = ("profile", "config_hash", "script", "executor_info")


def _run_with_record(tmp_path: Path) -> tuple[Workspace, Run]:
    """A run whose only provenance is the QUEUED e01 execution record."""
    ws = Workspace(tmp_path / "lab", name="Lab")
    ws.materialize()
    run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
    run.create_execution(
        profile_config=ProfileConfig({"nodes": 2}, name="cpu"),
        environment={"script": "/lab/s.py"},
        executor={"backend": "molq", "scheduler": "slurm", "scheduler_job_id": "4242"},
    )
    raw = json.loads((run.run_dir / "run.json").read_text())
    assert not any(key in raw for key in _RUN_LEVEL_PROVENANCE)
    return ws, run


def _wide_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render ``resources`` tables 200 columns wide so no cell is wrapped."""
    monkeypatch.setattr(resources, "_console", Console(width=200))


class TestRunList:
    def test_shows_latest_status_and_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, _run = _run_with_record(tmp_path)
        _wide_tables(monkeypatch)

        result = CliRunner().invoke(app, ["runs", "list", "p", "e", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert "cpu" in result.output
        assert "queued" in result.output


class TestRunInfo:
    def test_shows_provenance_and_attempt_ids(self, tmp_path: Path) -> None:
        ws, run = _run_with_record(tmp_path)

        result = CliRunner().invoke(
            app, ["runs", "info", "p", "e", run.id, "--workspace", str(ws.root)]
        )

        assert result.exit_code == 0, result.output
        assert "Profile: cpu" in result.output
        assert f"Config hash: {EXPECTED_HASH[:12]}" in result.output
        assert "e01" in result.output


class TestRunCancel:
    def test_all_lists_latest_executor_then_refuses_non_interactive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, _run = _run_with_record(tmp_path)
        _wide_tables(monkeypatch)

        result = CliRunner().invoke(
            app,
            [
                "runs",
                "cancel",
                "--project",
                "p",
                "--experiment",
                "e",
                "--all",
                "--workspace",
                str(ws.root),
            ],
        )

        assert result.exit_code == 1, result.output
        assert "slurm" in result.output
        assert "4242" in result.output
        assert "non-interactive" in result.output

    def test_status_filter_matches_latest_attempt_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, _run = _run_with_record(tmp_path)
        _wide_tables(monkeypatch)

        result = CliRunner().invoke(
            app,
            [
                "runs",
                "cancel",
                "--project",
                "p",
                "--experiment",
                "e",
                "--status",
                "queued",
                "--workspace",
                str(ws.root),
            ],
        )

        assert result.exit_code == 1, result.output
        assert "4242" in result.output
        assert "non-interactive" in result.output


class TestRunCreate:
    def test_new_run_reports_pending(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        ws.add_project("p").add_experiment("e")

        result = CliRunner().invoke(app, ["runs", "create", "p", "e", "--workspace", str(ws.root)])

        assert result.exit_code == 0, result.output
        assert "Status: pending" in result.output


class TestRetryRun:
    def test_rerun_reports_status_label(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1})
        sentinel = object()

        def fake_compiled_workflow_for_run(_run: Run) -> object:
            return sentinel

        def fake_execute(self: Run, workflow: object, /, **_kwargs: object) -> None:
            assert workflow is sentinel

        monkeypatch.setattr(
            "molab.workflow.compiled_workflow_for_run",
            fake_compiled_workflow_for_run,
            raising=False,
        )
        monkeypatch.setattr(Run, "execute", fake_execute)

        result = CliRunner().invoke(
            app, ["runs", "rerun", "p", "e", run.id, "--workspace", str(ws.root)]
        )

        assert result.exit_code == 0, result.output
        assert result.output.rstrip().endswith("status: pending")
