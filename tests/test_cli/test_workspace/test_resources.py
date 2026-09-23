"""CLI run harvest / analyze-failure gates."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from molab.cli.workspace import resources
from molab.knowledge import Finding
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
