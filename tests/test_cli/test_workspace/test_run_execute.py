"""``molab execute`` — the molq worker entry (``cli/workspace/run.py`` ``execute``).

The worker is what a scheduler job runs: it opens the run from its directory,
rebuilds the workflow from the experiment's ``workflow_entrypoint`` and
executes it against a pre-created Execution record. Invoked in-process through
typer's ``CliRunner``; the binding registry holds nothing for the experiment,
so recovery takes the same path a fresh worker process takes.

(Not named ``test_run.py``: neither this directory nor
``tests/test_server/test_routes/`` has an ``__init__.py``, and two
``test_run.py`` basenames collide in pytest's rootdir-relative import.)
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

import molab.cli
import molab.cli.workspace.run as run_module
import molab.workflow
from molab.profile import ProfileConfig
from molab.workspace import AgentRef, Workspace
from molab.workspace.domain import ExecutionMode
from molab.workspace.execution_repository import ExecutionRepository
from molab.workspace.project import Project
from molab.workspace.run import Run
from tests.support.journal import poison_node_output

_HEALING_MODULE = """\
from pathlib import Path

from molab.workflow import Workflow, WorkflowCompiler

FLAG = Path({flag!r})
RESULT = Path({result!r})

wf = Workflow(name="healing")


@wf.task
def stage_a(seed: int) -> int:
    return seed + 1


@wf.task(depends_on=["stage_a"])
def stage_b(stage_a: int) -> int:
    if not FLAG.exists():
        raise RuntimeError("not healed yet")
    RESULT.write_text(str(stage_a * 100))
    return stage_a * 100


workflow = WorkflowCompiler().compile(wf)
"""


def _healing_run(tmp_path: Path) -> tuple[Workspace, Project, Run]:
    """A ``{"seed": 1}`` run whose experiment points at ``healing_wf.py:workflow``."""
    wf_file = tmp_path / "healing_wf.py"
    wf_file.write_text(
        _HEALING_MODULE.format(
            flag=str(tmp_path / "healed"),
            result=str(tmp_path / "result.txt"),
        ),
        encoding="utf-8",
    )
    ws = Workspace(root=tmp_path / "ws", name="worker-lab")
    project = ws.add_project("p")
    exp = project.add_experiment("e")
    # Hand-written binding (arch-own-04 replaces this with Experiment.bind_workflow).
    exp.metadata = exp.metadata.model_copy(update={"workflow_entrypoint": f"{wf_file}:workflow"})
    exp.save()
    run = exp.add_run(params={"seed": 1})
    run.materialize()
    return ws, project, run


def _repository(ws: Workspace, project: Project, run: Run) -> ExecutionRepository:
    return ExecutionRepository(ws.root, run.run_dir, run_id=run.id, project_id=project.id, fs=ws.fs)


def _worker(run: Run, execution_id: str) -> int:
    result = CliRunner().invoke(
        molab.cli.app, ["execute", str(run.run_dir), "--execution-id", execution_id]
    )
    return result.exit_code


def _invoke(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(molab.cli.app, ["execute", *args])
    return result.exit_code, result.output


@dataclass
class _CompiledSpy:
    """What ``_execute_compiled`` was handed by the worker."""

    config: ProfileConfig | None = None
    bypass_cache: list[object] = field(default_factory=list)


def _spy_execute_compiled(monkeypatch: pytest.MonkeyPatch) -> _CompiledSpy:
    spy = _CompiledSpy()
    original: Callable[..., Awaitable[object]] = run_module._execute_compiled

    async def _wrapper(spec: object, **kwargs: object) -> object:
        run_context = kwargs["run_context"]
        config = getattr(run_context, "config", None)
        assert isinstance(config, ProfileConfig)
        spy.config = config
        spy.bypass_cache.append(kwargs.get("bypass_cache"))
        return await original(spec, **kwargs)

    monkeypatch.setattr(run_module, "_execute_compiled", _wrapper)
    return spy


_TEST_AGENT = AgentRef(id="test", type="person", name="test")


class TestExecute:
    def test_queued_execution_runs_to_success(self, tmp_path: Path) -> None:
        ws, project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        queued = _repository(ws, project, run).create(
            mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT
        )
        assert queued.id == "e01"
        assert [e.status.value for e in run.executions] == ["queued"]

        exit_code = _worker(run, "e01")

        assert exit_code == 0
        assert [e.status.value for e in run.executions] == ["succeeded"]
        assert len(run.executions) == 1
        assert (tmp_path / "result.txt").read_text() == "200"

    @pytest.mark.xfail(
        strict=True,
        raises=(ValueError, AssertionError),
        reason="arch-own-03: molab execute on a RESUME record — no checkpoint needed "
        "and the worker seeds from based_on e01, writing result 4100",
    )
    def test_resume_record_seeds_from_based_on(self, tmp_path: Path) -> None:
        ws, project, run = _healing_run(tmp_path)
        repository = _repository(ws, project, run)
        repository.create(mode=ExecutionMode.INITIAL, created_by=_TEST_AGENT)
        assert _worker(run, "e01") == 1
        assert [e.status.value for e in run.executions] == ["failed"]
        # e01 recorded stage_a == 2; the sentinel 41 reaches stage_b only as a
        # seed taken from e01's journal (a recompute yields 2 -> "200").
        poison_node_output(run.run_dir, "e01", "stage_a", 41)
        (tmp_path / "healed").write_text("ok")
        resume = repository.create(
            mode=ExecutionMode.RESUME,
            based_on_execution_id="e01",
            created_by=_TEST_AGENT,
        )
        assert resume.id == "e02"

        exit_code = _worker(run, "e02")

        assert exit_code == 0
        assert [e.status.value for e in run.executions] == ["failed", "succeeded"]
        assert (tmp_path / "result.txt").read_text() == "4100"

    def test_resolves_only_through_compiled_workflow_for_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, _project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        run.create_execution(
            environment={"script": str(tmp_path / "missing.py")},
            profile_config=ProfileConfig({"k": 1}, name="cpu"),
        )
        original = molab.workflow.compiled_workflow_for_run
        seen: list[str] = []

        def _counting(run_obj: Run) -> object:
            seen.append(run_obj.id)
            return original(run_obj)

        monkeypatch.setattr(molab.workflow, "compiled_workflow_for_run", _counting)

        exit_code = _worker(run, "e01")

        assert exit_code == 0
        assert seen == [run.id]
        assert run.execution("e01").status.value == "succeeded"
        assert (tmp_path / "result.txt").read_text() == "200"

    def test_config_comes_from_the_record(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, _project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        run.create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))
        spy = _spy_execute_compiled(monkeypatch)

        exit_code = _worker(run, "e01")

        assert exit_code == 0
        assert spy.config is not None
        assert spy.config.name == "cpu"
        assert spy.config.to_dict() == {"k": 1}
        assert spy.config.content_hash() == run.execution("e01").environment["config_hash"]
        assert "run_dir" not in spy.config.to_dict()
        assert spy.bypass_cache == [False]

    def test_bypass_cache_comes_from_the_record(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ws, _project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        run.create_execution(bypass_cache=True)
        spy = _spy_execute_compiled(monkeypatch)

        exit_code = _worker(run, "e01")

        assert exit_code == 0
        assert spy.bypass_cache == [True]

    @pytest.mark.parametrize("override", ["profile", "config"])
    def test_refuses_config_and_profile_overrides(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, override: str
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _ws, _project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        run.create_execution(profile_config=ProfileConfig({"k": 1}, name="cpu"))
        molcfg = tmp_path / "molcfg.json"
        molcfg.write_text(json.dumps({"profiles": {"cpu": {"k": 2}}}), encoding="utf-8")
        extra = ["--profile", "cpu"] if override == "profile" else ["--config", str(molcfg)]

        exit_code, output = _invoke(str(run.run_dir), "--execution-id", "e01", *extra)

        assert exit_code == 1, output
        assert "recorded" in output
        assert run.execution("e01").status.value == "queued"

    def test_missing_execution_id_is_a_usage_error(self, tmp_path: Path) -> None:
        _ws, _project, run = _healing_run(tmp_path)

        exit_code, output = _invoke(str(run.run_dir))

        assert exit_code == 2, output

    def test_unknown_execution_id_exits_1(self, tmp_path: Path) -> None:
        _ws, _project, run = _healing_run(tmp_path)
        (tmp_path / "healed").write_text("ok")
        run.create_execution()
        before = len(run.executions)

        exit_code, output = _invoke(str(run.run_dir), "--execution-id", "e09")

        assert exit_code == 1, output
        assert "e09" in output
        assert len(run.executions) == before
