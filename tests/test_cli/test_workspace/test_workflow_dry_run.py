"""``molab workflow dry-run`` (``cli/workflow_cmd.py``).

The command imports a script exactly as ``molab run`` does, under a scratch
root, and reports each bound workflow's plan. Nothing is written to the real
workspace — not a run, not an execution, not an index.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

import molab.cli
from molab.workflow import default_binding_registry
from molab.workspace import Workspace

_THREE_TASKS = """\
import molab as me
from molab.workflow import Workflow

wf = Workflow(name="pbix")


@wf.task
def monomers(seed: int) -> int:
    return seed


@wf.task
def pack(seed: int) -> int:
    return seed


@wf.task(depends_on=["monomers", "pack"])
def equilibrate(monomers: int, pack: int) -> int:
    return monomers + pack


ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf, params={{"seed": [1, 2]}})
"""

_BRANCHY = """\
import molab as me
from molab.workflow import Workflow

wf = Workflow(name="pipeline", entry="fetch")


@wf.task
async def fetch(ctx):
    return 1


@wf.task(depends_on=["fetch"], routes={{"ok": "publish", "fail": "rollback"}})
async def validate(ctx):
    return 2


@wf.task(depends_on=["validate"])
async def publish(ctx):
    return 3


@wf.task(depends_on=["validate"])
async def rollback(ctx):
    return 4


ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf)
"""

_BROKEN = """\
import molab as me
from molab.workflow import Workflow

wf = Workflow(name="broken")


@wf.task(depends_on=["ghost"])
def only(seed: int) -> int:
    return seed


ws = me.Workspace(name="lab")
ws.add_project("p").add_experiment("e").define(wf, params={{"seed": [1]}})
"""


@pytest.fixture(autouse=True)
def _isolate_cli_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Reset the process-global state a script import touches (as ``molab run`` does)."""
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


def _script(directory: Path, source: str = _THREE_TASKS) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "s.py"
    script.write_text(source.format(), encoding="utf-8")
    return script


def _molab(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(molab.cli.app, list(args))
    return result.exit_code, result.output


def _snapshot(directory: Path) -> list[str]:
    return sorted(str(p) for p in directory.rglob("*"))


def _json_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


class TestWorkflowDryRun:
    def test_reports_the_waves_and_writes_nothing(self, tmp_path: Path) -> None:
        script = _script(tmp_path / "lab")
        before = _snapshot(tmp_path)

        exit_code, output = _molab("workflow", "dry-run", str(script))

        assert exit_code == 0, output
        assert "Workflow:  pbix" in output
        assert "1. monomers, pack" in output
        assert "2. equilibrate" in output
        assert "equilibrate  <- monomers, pack" in output
        assert "not created yet" in output
        assert "nothing written" in output
        assert _snapshot(tmp_path) == before
        assert not (script.parent / "projects").exists()

    def test_json_is_one_object_per_experiment(self, tmp_path: Path) -> None:
        script = _script(tmp_path / "lab")
        before = _snapshot(tmp_path)

        exit_code, output = _molab("workflow", "dry-run", str(script), "--json")

        assert exit_code == 0, output
        [report] = _json_lines(output)
        assert report == {
            "experiment": {"id": None, "name": "e", "path": "projects/p/experiments/e"},
            "workflow": {"name": "pbix"},
            "waves": [["monomers", "pack"], ["equilibrate"]],
            "branches": [],
            "runs": [{"params": {"seed": 1}}, {"params": {"seed": 2}}],
            "tasks": [
                {"name": "monomers", "depends_on": []},
                {"name": "pack", "depends_on": []},
                {"name": "equilibrate", "depends_on": ["monomers", "pack"]},
            ],
        }
        assert _snapshot(tmp_path) == before

    def test_branches_are_listed_and_none_is_taken(self, tmp_path: Path) -> None:
        script = _script(tmp_path / "lab", _BRANCHY)

        exit_code, output = _molab("workflow", "dry-run", str(script), "--json")

        assert exit_code == 0, output
        [report] = _json_lines(output)
        assert report["waves"] == [["fetch"], ["validate"], ["publish", "rollback"]]
        assert report["branches"] == [
            {"source": "validate", "label": "ok", "target": "publish"},
            {"source": "validate", "label": "fail", "target": "rollback"},
        ]
        assert report["runs"] == [{"params": {}}]

    def test_an_existing_experiment_keeps_its_id_and_its_files(self, tmp_path: Path) -> None:
        root = tmp_path / "lab"
        ws = Workspace(root, name="lab")
        ws.materialize()
        exp = ws.add_project("p").add_experiment("e")
        script = _script(tmp_path / "elsewhere")
        before = _snapshot(root)

        exit_code, output = _molab("workflow", "dry-run", str(script), "--json", "-ws", str(root))

        assert exit_code == 0, output
        [report] = _json_lines(output)
        assert report["experiment"] == {
            "id": exp.id,
            "name": "e",
            "path": "projects/p/experiments/e",
        }
        assert report["runs"] == [{"params": {"seed": 1}}, {"params": {"seed": 2}}]
        assert _snapshot(root) == before
        assert exp.list_runs() == []

    def test_a_workflow_that_does_not_compile_exits_1_with_the_message(
        self, tmp_path: Path
    ) -> None:
        script = _script(tmp_path / "lab", _BROKEN)
        before = _snapshot(tmp_path)

        exit_code, output = _molab("workflow", "dry-run", str(script))

        assert exit_code == 1
        assert "ghost" in output
        assert _snapshot(tmp_path) == before
