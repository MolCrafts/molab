"""``molab run`` dispatch (``cli/workspace/run.py``).

Mirrors ``src/molab/cli/workspace/run.py``. Each class covers one private
function or command of that module: the dispatch-time Execution record
(``_create_dispatch_execution`` / ``_execute_selected`` / ``_dispatch_runs``),
the ``run`` command end to end in-process through typer's ``CliRunner``, the
``--scheduler`` path (``_submit_to_scheduler``, molq replaced by fakes), the
worker's run lookup (``_open_run``) and replica identity
(``_experiment_candidates`` / ``_select_candidate_runs``). No subprocess, no
real molq.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import molab.cli
from molab._run_display import read_run_json
from molab.cli._common import deterministic_run_id
from molab.cli.workspace.run import _submit_to_scheduler
from molab.profile import ProfileConfig
from molab.workflow import (
    Workflow,
    WorkflowCompiler,
    WorkflowRecoveryError,
    default_binding_registry,
)
from molab.workspace import Workspace
from molab.workspace.domain import Execution, ExecutionMode, ExecutionStatus
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.experiment import Experiment
from molab.workspace.project import Project
from molab.workspace.run import Run
from tests.support.journal import poison_node_output

_UUID7 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

# arch-own-00's healing workflow as a ``molab run`` script: stage_b fails until
# FLAG exists, then writes stage_a * 100 to RESULT (seed 1 -> "200").
_SCRIPT = """\
from pathlib import Path

import molab as me
from molab.workflow import Workflow

FLAG = Path({flag!r})
RESULT = Path({result!r})

wf = Workflow(name="healing")


@wf.task
def stage_a(seed: int) -> int:
    return seed + 1


@wf.task(depends_on=["stage_a"])
def stage_b(stage_a: int) -> str:
    if not FLAG.exists():
        raise RuntimeError("FLAG missing")
    RESULT.write_text(str(stage_a * 100))
    return str(stage_a * 100)


# ``define`` registers the workspace with ``molab.entry`` itself; an extra
# ``me.entry(ws)`` would list it twice and dispatch every run twice.
ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf, params={{"seed": [1]}})
"""


@pytest.fixture(autouse=True)
def _isolate_cli_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Reset the process-global state ``molab run`` touches.

    ``molab run`` imports the script as ``__main__`` (and puts its directory on
    ``sys.path``), registers workspaces in ``molab.entry`` and bindings in
    ``default_binding_registry``, and sets the CLI root override. The cwd is
    the test's tmp dir so ``submit_cwd`` and default-config discovery are
    hermetic.
    """
    from molab.entry import clear_registry
    from molab.workspace.workspace import set_cli_root_override

    saved_main = sys.modules.get("__main__")
    saved_path = list(sys.path)
    monkeypatch.chdir(tmp_path)
    clear_registry()
    default_binding_registry.clear()
    set_cli_root_override(None)
    try:
        yield
    finally:
        clear_registry()
        default_binding_registry.clear()
        set_cli_root_override(None)
        if saved_main is not None:
            sys.modules["__main__"] = saved_main
        sys.path[:] = saved_path


def _write_script(tmp_path: Path) -> Path:
    script = tmp_path / "s.py"
    script.write_text(
        _SCRIPT.format(flag=str(tmp_path / "healed"), result=str(tmp_path / "result.txt")),
        encoding="utf-8",
    )
    return script


def _heal(tmp_path: Path) -> None:
    (tmp_path / "healed").write_text("ok", encoding="utf-8")


def _molab(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(molab.cli.app, list(args))
    return result.exit_code, result.output


def _only_run(root: Path) -> Run:
    ws = Workspace.load(root)
    [project] = ws.list_projects()
    [exp] = project.list_experiments()
    [run] = exp.list_runs()
    return run


def _declared(tmp_path: Path, n_runs: int = 1) -> tuple[Workspace, Project, Experiment, list[Run]]:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    project = ws.add_project("p")
    exp = project.add_experiment("e")
    runs = [exp.add_run(params={"seed": seed}) for seed in range(1, n_runs + 1)]
    return ws, project, exp, runs


def _plain_script(tmp_path: Path) -> Path:
    script = tmp_path / "s.py"
    script.write_text("x = 1\n", encoding="utf-8")
    return script


def _fail(run: Run, execution_id: str) -> None:
    workspace = run.experiment.project.workspace
    ExecutionRepository(
        workspace.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=workspace.fs,
    ).seal(execution_id, ExecutionStatus.FAILED)


def _seal(run: Run, execution_id: str, status: ExecutionStatus) -> None:
    """Settle the QUEUED *execution_id* to terminal *status*."""
    workspace = run.experiment.project.workspace
    repository = ExecutionRepository(
        workspace.root,
        run.run_dir,
        run_id=run.id,
        project_id=run.experiment.project.id,
        fs=workspace.fs,
    )
    if status is ExecutionStatus.SUCCEEDED:
        repository.start(execution_id)
    repository.seal(execution_id, status)


def _capture_prints(monkeypatch: pytest.MonkeyPatch) -> object:
    """Record ``rprint`` from the run command as plain text."""
    from rich.console import Console

    from molab.cli.workspace import run as run_cli

    recording = Console(record=True, width=200)
    monkeypatch.setattr(run_cli, "rprint", recording.print)
    return recording


def _printed(recording: object) -> str:
    from rich.console import Console

    assert isinstance(recording, Console)
    return recording.export_text()


def _execute_run_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Delegating spy on ``molab.workflow.execute.execute_run``."""
    import molab.workflow as workflow_pkg
    import molab.workflow.execute as execute_mod

    original = execute_mod.execute_run
    seen: list[dict[str, object]] = []

    def wrapper(workflow: object, run: object, **kwargs: object) -> object:
        seen.append(dict(kwargs))
        return original(workflow, run, **kwargs)

    monkeypatch.setattr(execute_mod, "execute_run", wrapper)
    monkeypatch.setattr(workflow_pkg, "execute_run", wrapper, raising=False)
    return seen


def _bind_healing(tmp_path: Path) -> tuple[Project, Experiment, Run, Path, Path]:
    """In-process healing workflow: stage_b fails until FLAG exists.

    ``stage_a`` returns ``seed + 1``. With ``params={"seed": 1}`` a recompute
    writes ``"200"``; a seed of the poisoned predecessor output 41 writes
    ``"4100"``.
    """
    _ws, project, exp, [run] = _declared(tmp_path)
    flag = tmp_path / "healed"
    result = tmp_path / "result.txt"
    wf = Workflow(name="healing")

    @wf.task
    def stage_a(seed: int) -> int:
        return seed + 1

    @wf.task(depends_on=["stage_a"])
    def stage_b(stage_a: int) -> str:
        if not flag.exists():
            raise RuntimeError("FLAG missing")
        text = str(stage_a * 100)
        result.write_text(text)
        return text

    default_binding_registry.bind(exp, WorkflowCompiler().compile(wf))
    return project, exp, run, flag, result


def _fail_then_succeed(run: Run) -> None:
    """e01 failed, e02 succeeded — retryable, but the latest attempt is done."""
    run._create_execution()
    _seal(run, "e01", ExecutionStatus.FAILED)
    run._create_execution(mode=ExecutionMode.RERUN, predecessor="e01")
    _seal(run, "e02", ExecutionStatus.SUCCEEDED)


# seed 2 fails, seed 1 succeeds — one ``molab run`` with a mixed outcome.
_SPLIT_SCRIPT = """\
import molab as me
from molab.workflow import Workflow

wf = Workflow(name="split")


@wf.task
def only(seed: int) -> int:
    if seed == 2:
        raise RuntimeError("seed 2 fails")
    return seed


ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf, params={"seed": [1, 2]})
"""


# ── _create_dispatch_execution ────────────────────────────────────────────────


class TestCreateDispatchExecution:
    def test_plain_verb_creates_a_queued_initial_record_with_provenance(
        self, tmp_path: Path
    ) -> None:
        from molab.cli.workspace.run import _create_dispatch_execution
        from molab.workspace.execution_context import profile_config_hash

        _ws, _project, _exp, [run] = _declared(tmp_path)
        script = _plain_script(tmp_path)
        cfg = ProfileConfig({"k": 1}, name="cpu")

        execution_id = _create_dispatch_execution(
            run,
            continue_verb=None,
            fresh=False,
            profile_cfg=cfg,
            script=script,
            submit_cwd=str(tmp_path),
        )

        assert execution_id == "e01"
        record = run.execution("e01")
        assert record.mode.value == "initial"
        assert record.status.value == "queued"
        assert record.bypass_cache is False
        assert record.environment["script"] == str(script.resolve())
        assert record.environment["submit_cwd"]
        assert record.environment["config_hash"] == profile_config_hash(cfg)
        assert record.source is not None
        assert record.source.entrypoint == "s.py"

    def test_rerun_fresh_creates_a_rerun_record_that_bypasses_the_cache(
        self, tmp_path: Path
    ) -> None:
        from molab.cli.workspace.run import _create_dispatch_execution

        _ws, _project, _exp, [run] = _declared(tmp_path)
        script = _plain_script(tmp_path)
        run._create_execution()
        _fail(run, "e01")

        execution_id = _create_dispatch_execution(
            run,
            continue_verb="rerun",
            fresh=True,
            profile_cfg=ProfileConfig({}, name=None),
            script=script,
            submit_cwd=str(tmp_path),
        )

        assert execution_id == "e02"
        record = run.execution("e02")
        assert record.mode.value == "rerun"
        assert record.based_on_execution_id == "e01"
        assert record.bypass_cache is True

    def test_resume_creates_a_queued_record_based_on_the_latest_attempt(
        self, tmp_path: Path
    ) -> None:
        from molab.cli.workspace.run import _create_dispatch_execution

        _ws, _project, _exp, [run] = _declared(tmp_path)
        script = _plain_script(tmp_path)
        run._create_execution()
        _fail(run, "e01")

        execution_id = _create_dispatch_execution(
            run,
            continue_verb="resume",
            fresh=False,
            profile_cfg=ProfileConfig({}, name=None),
            script=script,
            submit_cwd=str(tmp_path),
        )

        assert execution_id == "e02"
        record = run.execution("e02")
        assert record.mode.value == "resume"
        assert record.based_on_execution_id == "e01"
        assert record.status.value == "queued"
        assert record.bypass_cache is False
        assert record.environment["script"] == str(script.resolve())

    def test_resume_based_on_a_succeeded_attempt_raises(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _create_dispatch_execution

        _ws, _project, _exp, [run] = _declared(tmp_path)
        _fail_then_succeed(run)

        with pytest.raises(ValueError, match="succeeded"):
            _create_dispatch_execution(
                run,
                continue_verb="resume",
                fresh=False,
                profile_cfg=ProfileConfig({}, name=None),
                script=_plain_script(tmp_path),
                submit_cwd=str(tmp_path),
            )

        assert len(run.executions) == 2


# ── _execute_selected ─────────────────────────────────────────────────────────


@dataclass
class _HandlerCall:
    run_id: str
    execution_id: str | None
    latest: Execution | None


@dataclass
class _SpyHandler:
    """A ``RunHandler`` that records what the dispatcher handed it."""

    raise_on_first: bool = False
    calls: list[_HandlerCall] = field(default_factory=list)

    def __call__(
        self,
        _script: Path,
        mol_run: Run,
        _experiment: Experiment,
        _project: Project,
        /,
        *,
        execution_id: str | None = None,
    ) -> None:
        executions = mol_run.executions
        self.calls.append(
            _HandlerCall(
                run_id=mol_run.id,
                execution_id=execution_id,
                latest=executions[-1] if executions else None,
            )
        )
        if self.raise_on_first and len(self.calls) == 1:
            raise RuntimeError("handler failed on the first run")


class TestExecuteSelected:
    @pytest.mark.parametrize("show_progress", [False, True])
    def test_handler_receives_the_queued_record_created_just_before_it(
        self, tmp_path: Path, show_progress: bool
    ) -> None:
        from molab.cli.workspace.run import _execute_selected

        _ws, project, exp, [run] = _declared(tmp_path)
        handler = _SpyHandler()

        _execute_selected(
            [(run, exp, project)],
            handler,
            _plain_script(tmp_path),
            show_progress=show_progress,
            continue_verb=None,
            fresh=False,
            profile_cfg=ProfileConfig({}, name=None),
            submit_cwd=str(tmp_path),
        )

        assert len(handler.calls) == 1
        call = handler.calls[0]
        assert call.execution_id == "e01"
        assert call.latest is not None
        assert call.latest.id == call.execution_id
        assert call.latest.status.value == "queued"

    def test_interrupted_batch_leaves_no_record_on_later_runs(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _execute_selected

        _ws, project, exp, [first, second] = _declared(tmp_path, n_runs=2)
        handler = _SpyHandler(raise_on_first=True)

        with pytest.raises(RuntimeError, match="first run"):
            _execute_selected(
                [(first, exp, project), (second, exp, project)],
                handler,
                _plain_script(tmp_path),
                show_progress=False,
                continue_verb=None,
                fresh=False,
                profile_cfg=ProfileConfig({}, name=None),
                submit_cwd=str(tmp_path),
            )

        assert [c.run_id for c in handler.calls] == [first.id]
        assert second.executions == []

    @pytest.mark.parametrize("show_progress", [False, True])
    def test_creation_value_error_is_a_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, show_progress: bool
    ) -> None:
        from molab.cli.workspace.run import _execute_selected

        _ws, project, exp, [run] = _declared(tmp_path)
        _fail_then_succeed(run)
        handler = _SpyHandler()
        printed = _capture_prints(monkeypatch)

        dispatched = _execute_selected(
            [(run, exp, project)],
            handler,
            _plain_script(tmp_path),
            show_progress=show_progress,
            continue_verb="resume",
            fresh=False,
            profile_cfg=ProfileConfig({}, name=None),
            submit_cwd=str(tmp_path),
        )

        assert handler.calls == []
        assert dispatched == []
        assert len(run.executions) == 2
        assert "skipped" in _printed(printed)

    def test_failed_run_beside_a_skip_is_dispatched(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _execute_selected

        _ws, project, exp, [skipped, failed] = _declared(tmp_path, n_runs=2)
        _fail_then_succeed(skipped)
        failed._create_execution()
        _seal(failed, "e01", ExecutionStatus.FAILED)
        handler = _SpyHandler()

        dispatched = _execute_selected(
            [(skipped, exp, project), (failed, exp, project)],
            handler,
            _plain_script(tmp_path),
            show_progress=False,
            continue_verb="resume",
            fresh=False,
            profile_cfg=ProfileConfig({}, name=None),
            submit_cwd=str(tmp_path),
        )

        assert [call.run_id for call in handler.calls] == [failed.id]
        assert handler.calls[0].execution_id == "e02"
        assert [item.id for item in dispatched] == [failed.id]
        assert len(skipped.executions) == 2


# ── _dispatch_runs ────────────────────────────────────────────────────────────


class TestDispatchRuns:
    def test_dry_run_creates_no_execution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.cli.workspace.run import _dispatch_runs

        ws, _project, exp, runs = _declared(tmp_path, n_runs=2)
        wf = Workflow(name="one")

        @wf.task
        def only(seed: int) -> int:
            return seed

        default_binding_registry.bind(exp, WorkflowCompiler().compile(wf))
        monkeypatch.setattr(
            "molab.cli.workspace.run._load_script_workspaces", lambda *_a, **_k: ([ws], None)
        )
        handler = _SpyHandler()

        n, selected = _dispatch_runs(
            script=_plain_script(tmp_path),
            profile_cfg=ProfileConfig({}, name=None),
            continue_verb=None,
            workspace=ws.root,
            explicit_workspace=True,
            run_handler=handler,
            mode_label="dry-run",
            dry_run=True,
        )

        assert n == 2
        assert sorted(r.id for r in selected) == sorted(r.id for r in runs)
        assert handler.calls == []
        for run in runs:
            assert run.executions == []

    def test_skipped_resume_is_not_counted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from molab.cli.workspace.run import _dispatch_runs

        ws, _project, exp, [run] = _declared(tmp_path)
        _fail_then_succeed(run)
        wf = Workflow(name="one")

        @wf.task
        def only(seed: int) -> int:
            return seed

        default_binding_registry.bind(exp, WorkflowCompiler().compile(wf))
        monkeypatch.setattr(
            "molab.cli.workspace.run._load_script_workspaces", lambda *_a, **_k: ([ws], None)
        )
        handler = _SpyHandler()

        n, selected = _dispatch_runs(
            script=_plain_script(tmp_path),
            profile_cfg=ProfileConfig({}, name=None),
            continue_verb="resume",
            workspace=ws.root,
            explicit_workspace=True,
            run_handler=handler,
            mode_label="local",
            dry_run=False,
        )

        assert (n, selected) == (0, [])
        assert handler.calls == []
        assert len(run.executions) == 2


# ── _make_local_inprocess_handler ─────────────────────────────────────────────


class TestMakeLocalInprocessHandler:
    def test_resume_seeds_completed_nodes_from_the_predecessor(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _make_local_inprocess_handler

        project, exp, run, flag, result = _bind_healing(tmp_path)
        handler = _make_local_inprocess_handler()
        script = _plain_script(tmp_path)
        initial = run.create_execution()
        assert initial.id == "e01"
        handler(script, run, exp, project, execution_id="e01")
        assert run.execution("e01").status.value == "failed"
        # e01 recorded stage_a == 2; 41 reaches stage_b only as a seed.
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        flag.write_text("ok", encoding="utf-8")
        resume = run.create_execution(mode=ExecutionMode.RESUME, based_on_execution_id="e01")
        assert resume.id == "e02"

        handler(script, run, exp, project, execution_id="e02")

        assert run.execution("e02").status.value == "succeeded"
        assert result.read_text(encoding="utf-8") == "4100"
        assert len(run.executions) == 2

    def test_failed_initial_returns_without_raising(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _make_local_inprocess_handler

        project, exp, run, _flag, _result = _bind_healing(tmp_path)
        queued = run.create_execution()
        assert queued.id == "e01"
        assert queued.status.value == "queued"
        assert queued.mode.value == "initial"

        _make_local_inprocess_handler()(
            _plain_script(tmp_path), run, exp, project, execution_id="e01"
        )

        assert run.execution("e01").status.value == "failed"

    def test_document_experiment_runs_the_queued_record(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _make_local_inprocess_handler

        default_binding_registry.clear()
        ws = Workspace(tmp_path / "ws", name="ws")
        project = ws.add_project("p")
        exp = project.add_experiment("calc")
        exp.bind_workflow(
            "document",
            document={
                "name": "constant_add",
                "task_configs": [
                    {
                        "task_id": "a",
                        "task_type": "core.constant",
                        "config": {"value": 2},
                        "status": "pending",
                    },
                    {
                        "task_id": "b",
                        "task_type": "core.constant",
                        "config": {"value": 3},
                        "status": "pending",
                    },
                    {"task_id": "c", "task_type": "core.add", "config": {}, "status": "pending"},
                ],
                "links": [
                    {"source": "a", "target": "c", "mapping": {}, "status": "pending"},
                    {"source": "b", "target": "c", "mapping": {}, "status": "pending"},
                ],
                "metadata": {"label": None, "description": None, "tags": [], "custom": {}},
            },
        )
        run = exp.add_run(params={"seed": 1})
        queued = run.create_execution()
        assert queued.id == "e01"
        assert queued.status.value == "queued"

        _make_local_inprocess_handler()(
            tmp_path / "unused.py", run, exp, project, execution_id="e01"
        )

        assert run.execution("e01").status.value == "succeeded"

    def test_unbound_experiment_leaves_the_record_queued(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _make_local_inprocess_handler

        default_binding_registry.clear()
        ws = Workspace(tmp_path / "ws", name="ws")
        project = ws.add_project("p")
        exp = project.add_experiment("bare")
        run = exp.add_run(params={"seed": 1})
        queued = run.create_execution()
        assert queued.status.value == "queued"

        with pytest.raises(WorkflowRecoveryError):
            _make_local_inprocess_handler()(
                tmp_path / "unused.py", run, exp, project, execution_id="e01"
            )

        assert run.execution("e01").status.value == "queued"


# ── run (command) ─────────────────────────────────────────────────────────────


class TestRun:
    def test_local_run_records_the_attempt_not_the_run(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        _heal(tmp_path)

        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))

        assert exit_code == 0, output
        run = _only_run(tmp_path)
        assert [(e.id, e.status.value) for e in run.executions] == [("e01", "succeeded")]
        run_dir = Path(run.run_dir)
        assert read_run_json(run_dir).get("script") is None
        assert not (run_dir / "source").exists()

    def test_profile_is_recorded_on_the_attempt(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        _heal(tmp_path)
        molcfg = tmp_path / "molcfg.json"
        molcfg.write_text(json.dumps({"profiles": {"cpu": {"k": 1}}}), encoding="utf-8")

        exit_code, output = _molab(
            "run",
            str(script),
            "--local",
            "--config",
            str(molcfg),
            "--profile",
            "cpu",
            "-ws",
            str(tmp_path),
        )

        assert exit_code == 0, output
        record = _only_run(tmp_path).execution("e01")
        assert record.environment["profile"] == "cpu"
        assert (
            record.environment["config_hash"] == ProfileConfig({"k": 1}, name="cpu").content_hash()
        )

    def test_rerun_after_failure_opens_a_rerun_execution(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))
        assert exit_code == 1, output
        assert [e.status.value for e in _only_run(tmp_path).executions] == ["failed"]
        _heal(tmp_path)

        exit_code, output = _molab("run", str(script), "--rerun", "--local", "-ws", str(tmp_path))

        assert exit_code == 0, output
        executions = _only_run(tmp_path).executions
        assert len(executions) == 2
        second = executions[1]
        assert second.id == "e02"
        assert second.mode.value == "rerun"
        assert second.based_on_execution_id == "e01"
        assert second.status.value == "succeeded"

    def test_rerun_fresh_bypasses_the_cache_from_the_record(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        script = _write_script(tmp_path)
        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))
        assert exit_code == 1, output
        _heal(tmp_path)
        seen = _execute_run_calls(monkeypatch)

        exit_code, output = _molab(
            "run", str(script), "--rerun", "--fresh", "--local", "-ws", str(tmp_path)
        )

        assert exit_code == 0, output
        assert _only_run(tmp_path).execution("e02").bypass_cache is True
        assert seen == [{"execution_id": "e02"}]

    def test_resume_after_failure_opens_a_resume_execution(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))
        assert exit_code == 1, output
        _heal(tmp_path)

        exit_code, output = _molab("run", str(script), "--resume", "--local", "-ws", str(tmp_path))

        assert exit_code == 0, output
        executions = _only_run(tmp_path).executions
        assert [e.mode.value for e in executions] == ["initial", "resume"]
        assert [e.based_on_execution_id for e in executions] == [None, "e01"]
        assert [e.status.value for e in executions] == ["failed", "succeeded"]

    def test_rerun_fresh_after_resume(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))
        assert exit_code == 1, output
        _heal(tmp_path)
        exit_code, output = _molab("run", str(script), "--resume", "--local", "-ws", str(tmp_path))
        assert exit_code == 0, output

        exit_code, output = _molab(
            "run", str(script), "--rerun", "--fresh", "--local", "-ws", str(tmp_path)
        )

        assert exit_code == 0, output
        third = _only_run(tmp_path).execution("e03")
        assert third.mode.value == "rerun"
        assert third.based_on_execution_id == "e02"
        assert third.bypass_cache is True

    def test_rerun_after_success_opens_a_rerun_execution(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        _heal(tmp_path)
        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))
        assert exit_code == 0, output
        assert [item.status.value for item in _only_run(tmp_path).executions] == ["succeeded"]

        exit_code, output = _molab("run", str(script), "--rerun", "--local", "-ws", str(tmp_path))

        assert exit_code == 0, output
        executions = _only_run(tmp_path).executions
        assert [item.id for item in executions] == ["e01", "e02"]
        assert executions[1].mode.value == "rerun"
        assert executions[1].based_on_execution_id == "e01"
        assert executions[1].status.value == "succeeded"

    def test_resume_skips_run_whose_latest_attempt_succeeded(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path)
        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))
        assert exit_code == 1, output
        _heal(tmp_path)
        exit_code, output = _molab("run", str(script), "--rerun", "--local", "-ws", str(tmp_path))
        assert exit_code == 0, output
        assert [item.status.value for item in _only_run(tmp_path).executions] == [
            "failed",
            "succeeded",
        ]

        exit_code, output = _molab("run", str(script), "--resume", "--local", "-ws", str(tmp_path))

        assert exit_code == 0, output
        assert "skipped" in output
        assert "No runs resumed." in output
        assert len(_only_run(tmp_path).executions) == 2

    def test_one_failed_run_of_two_exits_1(self, tmp_path: Path) -> None:
        script = tmp_path / "split.py"
        script.write_text(_SPLIT_SCRIPT, encoding="utf-8")

        exit_code, output = _molab("run", str(script), "--local", "-ws", str(tmp_path))

        assert exit_code == 1, output
        assert "1 of 2 runs did not succeed" in output
        [project] = Workspace.load(tmp_path).list_projects()
        [exp] = project.list_experiments()
        statuses = sorted(
            (run.metadata.parameters["seed"], [e.status.value for e in run.executions])
            for run in exp.list_runs()
        )
        assert statuses == [(1, ["succeeded"]), (2, ["failed"])]


# ── _report_local_results ─────────────────────────────────────────────────────


class TestReportLocalResults:
    def test_a_later_attempt_is_the_label(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.cli.workspace.run import _report_local_results

        _ws, _project, _exp, [run] = _declared(tmp_path)
        run._create_execution()
        _seal(run, "e01", ExecutionStatus.SUCCEEDED)
        # A later attempt is queued. status_label is that attempt, not e01.
        run._create_execution(mode=ExecutionMode.RERUN, predecessor="e01")
        printed = _capture_prints(monkeypatch)

        with pytest.raises(typer.Exit) as excinfo:
            _report_local_results([(run, "e01")], None)

        assert excinfo.value.exit_code == 1
        assert "status=queued" in _printed(printed)

    def test_a_later_success_exits_0(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from molab.cli.workspace.run import _report_local_results

        _ws, _project, _exp, [run] = _declared(tmp_path)
        run._create_execution()
        _seal(run, "e01", ExecutionStatus.FAILED)
        run._create_execution(mode=ExecutionMode.RERUN, predecessor="e01")
        _seal(run, "e02", ExecutionStatus.SUCCEEDED)
        printed = _capture_prints(monkeypatch)

        _report_local_results([(run, "e01")], None)

        assert "OK 1 runs completed." in _printed(printed)
        assert run.status_label == "succeeded"
        assert run.has_failures is True

    def test_resume_without_an_id_judges_the_latest_attempt(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _report_local_results

        _ws, _project, _exp, [run] = _declared(tmp_path)
        run._create_execution()
        _seal(run, "e01", ExecutionStatus.FAILED)
        run._create_execution(mode=ExecutionMode.RERUN, predecessor="e01")
        _seal(run, "e02", ExecutionStatus.SUCCEEDED)

        _report_local_results([(run, None)], "resume")

    def test_successful_resume_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.cli.workspace.run import _report_local_results

        _ws, _project, _exp, [run] = _declared(tmp_path)
        _fail_then_succeed(run)
        printed = _capture_prints(monkeypatch)

        _report_local_results([(run, "e02")], "resume")

        assert "OK 1 runs resumed." in _printed(printed)
        assert run.status_label == "succeeded"
        assert run.has_failures is True

    def test_failed_latest_attempt_names_the_error_not_error_txt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from molab.cli.workspace.run import _report_local_results

        _ws, _project, _exp, [run] = _declared(tmp_path)
        with pytest.raises(RuntimeError, match="FLAG missing"), run.start():
            raise RuntimeError("FLAG missing")
        printed = _capture_prints(monkeypatch)

        with pytest.raises(typer.Exit) as excinfo:
            _report_local_results([(run, "e01")], None)

        assert excinfo.value.exit_code == 1
        text = _printed(printed)
        assert "FLAG missing" in text
        assert "error.txt" not in text

    def test_empty_dispatch_says_no_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from molab.cli.workspace.run import _report_local_results

        printed = _capture_prints(monkeypatch)

        _report_local_results([], None)

        assert "No runs" in _printed(printed)


# ── _failure_detail ───────────────────────────────────────────────────────────


class TestFailureDetail:
    def test_names_the_recorded_error_and_evidence_directory(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _failure_detail

        _ws, _project, _exp, [run] = _declared(tmp_path)
        with pytest.raises(RuntimeError, match="FLAG missing"), run.start():
            raise RuntimeError("FLAG missing")

        assert _failure_detail(run) == (
            f"RuntimeError: FLAG missing (Execution evidence under {run.execution_dir('e01')})"
        )

    def test_no_attempts_returns_none(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _failure_detail

        _ws, _project, _exp, [run] = _declared(tmp_path)

        assert _failure_detail(run) is None


# ── _submit_to_scheduler ──────────────────────────────────────────────────────
# Moved verbatim from arch-own-02d's tests/test_cli/test_workspace/test_run_submit.py
# (SubmitSpy / SchedulerFixture / _install_fake_submitor / scheduler_fixture).


@dataclass
class SubmitSpy:
    """What the fake ``Submitor`` saw inside ``submit_job``."""

    submits: int = 0
    execution_id: str | None = None
    record_at_submit: Execution | None = None
    record_error: str | None = None


@dataclass
class SchedulerFixture:
    ws: Workspace
    run: Run
    script: Path
    spy: SubmitSpy


def _install_fake_submitor(monkeypatch: pytest.MonkeyPatch, run: Run) -> SubmitSpy:
    spy = SubmitSpy()

    class _FakeEventBus:
        def on(self, evt: object, handler: object) -> None:
            del evt, handler

    class _FakeJob:
        job_id = "fake-job-id"
        scheduler_job_id = "fake-sched-id"

    class FakeSubmitor:
        def __init__(self, _cluster: object, *, jobs_dir: str) -> None:
            del jobs_dir
            self._event_bus = _FakeEventBus()

        def __enter__(self) -> FakeSubmitor:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

        def submit_job(
            self,
            *,
            resources: object,
            scheduling: object,
            execution: object,
            metadata: dict[str, str],
            argv: list[str] | None = None,
            script: object | None = None,
        ) -> _FakeJob:
            del resources, scheduling, execution, argv, script
            spy.submits += 1
            spy.execution_id = metadata["execution_id"]
            try:
                spy.record_at_submit = run.execution(metadata["execution_id"])
            except KeyError as exc:
                spy.record_error = f"no record for {metadata['execution_id']!r}: {exc}"
            return _FakeJob()

    monkeypatch.setattr("molq.Submitor", FakeSubmitor)
    return spy


@pytest.fixture
def scheduler_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[SchedulerFixture]:
    """A declared ``{"seed": 1}`` run whose only attempt ``e01`` was cancelled."""
    ws = Workspace(tmp_path / "ws")
    ws.materialize()
    project = ws.add_project("p")
    exp = project.add_experiment("e")
    run = exp.add_run(params={"seed": 1})
    run._create_execution()
    run.cancel("e01")

    script = tmp_path / "s.py"
    script.write_text("x = 1\n", encoding="utf-8")

    wf = Workflow(name="one")

    @wf.task
    def only(seed: int) -> int:
        return seed

    compiled = WorkflowCompiler().compile(wf)
    default_binding_registry.bind(exp, compiled)
    # A scheduler worker re-imports the workflow, so submission needs a locator.
    exp.bind_workflow(
        "code",
        entrypoint=f"{script}:wf",
        document=compiled.to_graph_ir().model_dump(mode="json"),
    )
    monkeypatch.setattr(
        "molab.cli.workspace.run._load_script_workspaces", lambda *_a, **_k: ([ws], None)
    )
    monkeypatch.setattr(
        "molab.plugins.submit_molq.metadata.supported_schedulers", lambda: ("local",)
    )
    spy = _install_fake_submitor(monkeypatch, run)
    try:
        yield SchedulerFixture(ws=ws, run=run, script=script, spy=spy)
    finally:
        default_binding_registry.unbind(exp)


class TestSubmitToScheduler:
    def test_rerun_fresh_submits_queued_record_with_bypass_cache(
        self, scheduler_fixture: SchedulerFixture
    ) -> None:
        fx = scheduler_fixture

        _submit_to_scheduler(
            script=fx.script,
            profile_cfg=ProfileConfig({}, name=None),
            continue_verb="rerun",
            target_path=fx.ws.root,
            explicit_ws=True,
            selected_target=None,
            selected_scheduler="local",
            cluster=None,
            resources={},
            scheduling={},
            block=False,
            fresh=True,
        )

        assert fx.spy.execution_id == "e02"
        assert fx.spy.record_error is None, fx.spy.record_error
        record = fx.spy.record_at_submit
        assert record is not None
        assert record.status.value == "queued"
        assert record.mode.value == "rerun"
        assert record.based_on_execution_id == "e01"
        assert record.bypass_cache is True
        run_dir = Path(fx.run.run_dir)
        assert list(run_dir.rglob("fresh.json")) == []
        assert sorted(p.name for p in (run_dir / "executions").iterdir()) == ["e01", "e02"]

    def test_resume_hands_a_queued_resume_record(
        self, monkeypatch: pytest.MonkeyPatch, scheduler_fixture: SchedulerFixture
    ) -> None:
        fx = scheduler_fixture
        recorder = _SpyHandler()
        monkeypatch.setattr(
            "molab.plugins.submit_molq.submit.make_submit_handler", lambda **_kw: recorder
        )
        monkeypatch.setattr(
            "molab.plugins.submit_molq.metadata.supported_schedulers", lambda: ["slurm"]
        )

        _submit_to_scheduler(
            script=fx.script,
            profile_cfg=ProfileConfig({}, name=None),
            continue_verb="resume",
            target_path=fx.ws.root,
            explicit_ws=True,
            selected_target=None,
            selected_scheduler="slurm",
            cluster=None,
            resources={},
            scheduling={},
            block=False,
        )

        assert len(recorder.calls) == 1
        call = recorder.calls[0]
        assert call.execution_id == "e02"
        assert call.latest is not None
        assert call.latest.id == "e02"
        assert call.latest.status.value == "queued"
        assert call.latest.mode.value == "resume"
        assert call.latest.based_on_execution_id == "e01"


# ── _open_run ─────────────────────────────────────────────────────────────────


class TestOpenRun:
    def test_opens_run_and_experiment_from_the_run_directory(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _open_run

        _ws, _project, exp, [run] = _declared(tmp_path)
        assert Path(run.run_dir).name != run.id

        opened_run, opened_exp = _open_run(Path(run.run_dir))

        assert opened_run.id == run.id
        assert opened_exp.id == exp.id

    def test_no_workspace_above_exits_1(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _open_run

        run_dir = tmp_path / "stray" / "runs" / "seed=1"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(json.dumps({"id": "r1"}), encoding="utf-8")

        with pytest.raises(typer.Exit) as excinfo:
            _open_run(run_dir)

        assert excinfo.value.exit_code == 1

    def test_run_json_without_id_exits_1(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _open_run

        _ws, _project, _exp, [run] = _declared(tmp_path)
        run_json = Path(run.run_dir) / "run.json"
        data = json.loads(run_json.read_text(encoding="utf-8"))
        del data["id"]
        run_json.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(typer.Exit) as excinfo:
            _open_run(Path(run.run_dir))

        assert excinfo.value.exit_code == 1


# ── _experiment_candidates ────────────────────────────────────────────────────


def _replica_experiment(tmp_path: Path) -> Experiment:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    return ws.add_project("p").add_experiment("r", n_replicas=1, seeds=[7])


def _legacy_run(exp: Experiment, cfg: ProfileConfig) -> Run:
    """A replica run under HEAD's profile-aware 16-hex id."""
    assert cfg.name is not None
    return exp.add_run(
        params={"seed": 7, "replica": 0},
        id=deterministic_run_id(
            {"seed": 7, "replica": 0, "_profile": cfg.name, "_config_hash": cfg.content_hash()}
        ),
    )


class TestExperimentCandidates:
    def test_legacy_replica_run_is_found_by_its_id(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _experiment_candidates
        from molab.workspace.execution_context import profile_config_hash

        exp = _replica_experiment(tmp_path)
        cfg = ProfileConfig({"n": 1}, name="cpu")
        legacy = _legacy_run(exp, cfg)

        [(existing, _params, config_hash, _label)], _declared_runs, _total = _experiment_candidates(
            exp, cfg
        )

        assert existing is not None
        assert existing.id == legacy.id
        assert config_hash == profile_config_hash(cfg)

    def test_empty_unnamed_profile_has_no_config_hash(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _experiment_candidates

        exp = _replica_experiment(tmp_path)

        [(_existing, _params, config_hash, _label)], _declared_runs, _total = (
            _experiment_candidates(exp, ProfileConfig({}, name=None))
        )

        assert config_hash is None

    def test_unnamed_nonempty_profile_folds_its_content_hash(self, tmp_path: Path) -> None:
        from molab.cli.workspace.run import _experiment_candidates

        exp = _replica_experiment(tmp_path)
        cfg = ProfileConfig({"n": 1}, name=None)

        [(_existing, _params, config_hash, _label)], _declared_runs, _total = (
            _experiment_candidates(exp, cfg)
        )

        assert config_hash == ProfileConfig({"n": 1}, name=None).content_hash()


# ── _select_candidate_runs ────────────────────────────────────────────────────


def _select_round(exp: Experiment, cfg: ProfileConfig, continue_verb: str | None) -> list[Run]:
    from molab.cli.workspace.run import _experiment_candidates, _select_candidate_runs

    candidates, _declared_runs, _total = _experiment_candidates(exp, cfg)
    selected = _select_candidate_runs(candidates, exp=exp, continue_verb=continue_verb)
    return [run for run, _label in selected]


class TestSelectCandidateRuns:
    def test_replica_run_is_created_once_by_definition(self, tmp_path: Path) -> None:
        from molab.workspace.execution_context import profile_config_hash
        from molab.workspace.run import compute_run_definition_hash

        exp = _replica_experiment(tmp_path)
        cfg = ProfileConfig({"n": 1}, name="cpu")

        [first] = _select_round(exp, cfg, None)
        [second] = _select_round(exp, cfg, None)

        assert first.id == second.id
        assert _UUID7.match(first.id), first.id
        assert len(exp.list_runs()) == 1
        assert first.executions == []
        assert first.metadata.definition_hash == compute_run_definition_hash(
            experiment_revision_id=exp.metadata.revision_id,
            parameters={"seed": 7, "replica": 0},
            config_hash=profile_config_hash(cfg),
        )

    def test_different_config_content_is_a_different_run(self, tmp_path: Path) -> None:
        exp = _replica_experiment(tmp_path)

        [first] = _select_round(exp, ProfileConfig({"n": 1}, name="cpu"), None)
        [second] = _select_round(exp, ProfileConfig({"n": 2}, name="cpu"), None)

        assert first.id != second.id
        assert len(exp.list_runs()) == 2

    def test_legacy_replica_run_is_reused(self, tmp_path: Path) -> None:
        exp = _replica_experiment(tmp_path)
        cfg = ProfileConfig({"n": 1}, name="cpu")
        legacy = _legacy_run(exp, cfg)

        [selected] = _select_round(exp, cfg, None)

        assert selected.id == legacy.id
        assert len(exp.list_runs()) == 1

    def test_rerun_on_an_empty_experiment_selects_and_creates_nothing(self, tmp_path: Path) -> None:
        exp = _replica_experiment(tmp_path)

        selected = _select_round(exp, ProfileConfig({"n": 1}, name="cpu"), "rerun")

        assert selected == []
        assert len(exp.list_runs()) == 0


class TestRunHelpText:
    def test_resume_help_opens_a_new_execution(self) -> None:
        code, out = _molab("run", "--help")

        assert code == 0
        assert "new RESUME Execution" in out
        assert "Reopen" not in out

    def test_worker_help_does_not_name_a_run_id_directory(self) -> None:
        code, out = _molab("execute", "--help")

        assert code == 0
        assert "run-<id>" not in out
