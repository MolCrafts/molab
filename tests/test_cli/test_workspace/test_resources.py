"""CLI run commands: the harvest gate and the run readers."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

from molab.cli import app
from molab.cli.workspace import resources
from molab.knowledge import Finding, Observation, Report
from molab.profile import ProfileConfig
from molab.workflow import RunFailedError, Workflow
from molab.workspace import Workspace
from molab.workspace.run import Run
from tests.support.records import read_record


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
        assert "HARVEST_TARGETS" in src
        assert "--of" in src
        assert "Finding, Observation, or Report" in src

    def test_note_exits_with_the_harvest_gate(self, tmp_path: Path) -> None:
        ws, exp, run = _failed_run(tmp_path)
        result = CliRunner().invoke(
            resources.run_app,
            [
                "harvest",
                exp.project.id,
                exp.id,
                run.id,
                "narrative body",
                "--of",
                "Note",
                "--workspace",
                str(ws.root),
            ],
        )
        assert result.exit_code == 1, result.output
        assert "harvest --of must be Finding, Observation, or Report" in result.stdout

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
    """The CLI harvests through ``Finding.harvest`` (or Observation / Report).

    The workspace ``Run`` has no harvest method. The class is the verb.
    """

    def test_calls_the_knowledge_verb_with_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws, exp, run = _failed_run(tmp_path)

        calls: list[dict[str, Any]] = []

        def probe_for(of: type) -> Any:
            def probe(target: Any, **kwargs: Any) -> Any:
                calls.append({"target": target, "of": of, **kwargs})
                return SimpleNamespace(name="probe")

            return probe

        assert not hasattr(Run, "harvest")
        for cls in (Finding, Observation, Report):
            monkeypatch.setattr(cls, "harvest", probe_for(cls))

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

        calls: list[Any] = []

        def probe(*args: Any, **_kwargs: Any) -> Any:
            calls.append(args)
            return SimpleNamespace(name="probe")

        for cls in (Finding, Observation, Report):
            monkeypatch.setattr(cls, "harvest", probe)

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
        assert not hasattr(resources, "run_analyze_failure")


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
    run._create_execution(
        profile_config=ProfileConfig({"nodes": 2}, name="cpu"),
        environment={"script": "/lab/s.py"},
        executor={"backend": "molq", "scheduler": "slurm", "scheduler_job_id": "4242"},
    )
    raw = read_record(run.run_dir)
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

    def test_failed_run_shows_execution_error(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        run = ws.add_project("p").add_experiment("e").add_run()
        try:
            with run.start():
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        result = CliRunner().invoke(
            app, ["runs", "info", "p", "e", run.id, "--workspace", str(ws.root)]
        )

        assert result.exit_code == 0, result.output
        assert "Error: RuntimeError: boom" in result.output


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


def _healing_workflow(flag: Path) -> Workflow:
    """stage_b raises until *flag* exists; stage_a is ``seed + 1``."""
    wf = Workflow(name="healing")

    @wf.task
    def stage_a(seed: int) -> int:
        return seed + 1

    @wf.task(depends_on=["stage_a"])
    def stage_b(stage_a: int) -> str:
        if not flag.exists():
            raise RuntimeError("FLAG missing")
        return str(stage_a * 100)

    return wf


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

    def test_resume_after_failure_reports_succeeded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = Workspace(tmp_path / "lab", name="Lab")
        ws.materialize()
        run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
        flag = tmp_path / "healed"
        wf = _healing_workflow(flag)
        compiled = (wf).compile()

        with pytest.raises(RunFailedError):
            run.execute(wf)

        flag.write_text("ok", encoding="utf-8")
        monkeypatch.setattr("molab.workflow.compiled_workflow_for_run", lambda _run: compiled)

        result = CliRunner().invoke(
            app, ["runs", "resume", "p", "e", run.id, "--workspace", str(ws.root)]
        )

        assert result.exit_code == 0, result.output
        assert "status: succeeded" in result.output
        assert [item.mode.value for item in run.executions] == ["initial", "resume"]
        assert run.status_label == "succeeded"
        assert run.has_failures is True


def _greeting(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    source = tmp_path / "hello.txt"
    source.write_bytes(b"hello\n")
    asset = ws.assets.import_asset("greeting", source)
    return ws, asset.id


class TestAssetList:
    def test_shows_title_and_kind(self, tmp_path: Path) -> None:
        ws, _asset_id = _greeting(tmp_path)
        result = CliRunner().invoke(resources.asset_app, ["list", "-ws", str(ws.root)])
        assert result.exit_code == 0, result.output
        assert "greeting" in result.output
        assert "text/plain" in result.output


class TestAssetInfo:
    def test_shows_ref_media_type_digest_and_origin(self, tmp_path: Path) -> None:
        ws, asset_id = _greeting(tmp_path)
        result = CliRunner().invoke(resources.asset_app, ["info", asset_id, "-ws", str(ws.root)])
        assert result.exit_code == 0, result.output
        assert f"molab:asset/{asset_id}" in result.output
        assert "text/plain" in result.output
        assert "sha256:" in result.output
        assert "import" in result.output
        assert "greeting" in result.output

    def test_unknown_id_exits_1(self, tmp_path: Path) -> None:
        ws, _asset_id = _greeting(tmp_path)
        result = CliRunner().invoke(resources.asset_app, ["info", "missing", "-ws", str(ws.root)])
        assert result.exit_code == 1


class TestAssetLineage:
    def test_produced_asset_points_at_the_run_input(self, tmp_path: Path) -> None:
        ws = Workspace(tmp_path / "ws", name="lab")
        ws.materialize()
        source = tmp_path / "hello.txt"
        source.write_bytes(b"hello\n")
        upstream = ws.add_project("p").assets.import_asset("raw", source)
        experiment = ws.project("p").add_experiment("e")
        run = experiment.add_run(inputs=(upstream.id,))
        with run.start() as ctx:
            produced = ctx.register(b"done\n", title="result.txt")
        result = CliRunner().invoke(
            resources.asset_app, ["lineage", produced.id, "-ws", str(ws.root)]
        )
        assert result.exit_code == 0, result.output
        assert f"<- {upstream.id}" in result.output


class TestAssetDelete:
    def _delete(self, ws: Workspace, spec: str):
        return CliRunner().invoke(resources.asset_app, ["delete", spec, "-ws", str(ws.root)])

    def test_by_id(self, tmp_path: Path) -> None:
        ws, asset_id = _greeting(tmp_path)
        result = self._delete(ws, asset_id)
        assert result.exit_code == 0, result.output
        assert result.output.startswith(f"deleted\tgreeting\t{asset_id}\t")
        assert ws.assets.list() == []
        assert not (Path(str(ws.root)) / "assets" / "greeting").exists()

    def test_by_ref(self, tmp_path: Path) -> None:
        ws, asset_id = _greeting(tmp_path)
        result = self._delete(ws, f"molab:asset/{asset_id}")
        assert result.exit_code == 0, result.output
        assert ws.assets.list() == []

    def test_by_directory(self, tmp_path: Path) -> None:
        ws, _asset_id = _greeting(tmp_path)
        result = self._delete(ws, "assets/greeting")
        assert result.exit_code == 0, result.output
        assert ws.assets.list() == []

    def test_refuses_when_cited_and_names_the_document(self, tmp_path: Path) -> None:
        from molab.knowledge import Note
        from molab.knowledge.write import write_knowledge

        ws, asset_id = _greeting(tmp_path)
        write_knowledge(
            ws.root,
            name="greeting-notes",
            of=Note,
            created_by="test",
            text=f"See [greeting](molab:asset/{asset_id}).\n",
        )
        result = self._delete(ws, asset_id)
        assert result.exit_code == 1
        assert "greeting-notes" in " ".join(result.output.split())
        assert [asset.id for asset in ws.assets.list()] == [asset_id]

    def test_unknown_id_exits_1(self, tmp_path: Path) -> None:
        ws, asset_id = _greeting(tmp_path)
        result = self._delete(ws, "missing")
        assert result.exit_code == 1
        assert "not found" in result.output
        assert [asset.id for asset in ws.assets.list()] == [asset_id]
