"""CLI run harvest / analyze-failure gates."""

from __future__ import annotations

import inspect
from pathlib import Path

from typer.testing import CliRunner

from molab.cli.workspace import resources
from molab.workspace import Workspace


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


class TestRunAnalyzeFailure:
    def test_prints_report(self) -> None:
        src = inspect.getsource(resources.run_analyze_failure)
        assert "Report:" in src
        assert "FailureAnalysis" not in src
