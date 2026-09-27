"""Public-API goldens for drop-harness-01-src.

The Python harness is deleted (D86): molab boots, serves and runs science with
no plugin at all, and no core seam survives that only the harness used.

1. ``import molab`` loads no LLM SDK: neither ``pydantic_ai`` nor
   ``pydantic_graph`` is in ``sys.modules``.
2. The deleted modules are gone: ``importlib.util.find_spec`` returns ``None``
   for ``molab.harness``, ``molab.server.shutdown``,
   ``molab.workspace.curation``, ``molab.plugins.extras`` and
   ``molab.cli.workspace.mcp_config``.
3. molab registers nothing of its own in the ``molab.cli_plugins`` /
   ``molab.server_plugins`` entry-point groups.
4. The OpenAPI surface of ``create_app(serve_static=False)`` carries a core
   subset and no harness path (no ``/api/agent*`` / ``/api/approvals*`` /
   ``/api/plans*``, nothing containing ``/plan-tasks`` / ``/plans`` /
   ``curate``). The total path count is deliberately not asserted.
5. The CLI carries ``run`` / ``serve`` / ``runs`` and none of ``plan`` /
   ``agent`` / ``curate`` / ``harness`` / ``mcp``.
6. ``molab.workflow`` has no ``set_workflow_recoverer``; recovering a run whose
   experiment records no entrypoint raises ``WorkflowRecoveryError`` naming
   ``workflow_entrypoint`` and never ``molab plan``.
7. ``molab.services.operator_config`` keeps ``load_operator_config`` but not
   ``bridge_operator_config``; ``molab.knowledge`` has no ``PLAN_BOOK_NAME``.
8. A one-task workflow defined with ``params={"seed": [0]}`` executes through
   ``Run.execute`` to ``by_status == {"succeeded": 1}``.

Expected stdout (exactly this line, exit code 0):

    drop-harness-01-src: ok

Provenance: goldens hard-coded from the spec
``.claude/specs/drop-harness-01-src.md`` (Testing strategy, "Regression
example") and molab's own behaviour (no third-party oracle), recorded
2026-09-27 on branch feat/knowledge-crossref. The workspace is an in-process
temporary directory — no subprocess, no network, no third-party runtime.
"""

from __future__ import annotations

import sys

import molab

# Golden 1 is checked before anything else is imported, so the probe sees what
# ``import molab`` alone pulled in.
_LOADED_AFTER_IMPORT = sorted(m for m in ("pydantic_ai", "pydantic_graph") if m in sys.modules)

import importlib.metadata  # noqa: E402
import importlib.util  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import typer.main  # noqa: E402

import molab.cli  # noqa: E402
import molab.knowledge  # noqa: E402
import molab.services.operator_config  # noqa: E402
import molab.workflow  # noqa: E402
from molab.server.app import create_app  # noqa: E402
from molab.workflow import (  # noqa: E402
    TaskContext,
    Workflow,
    WorkflowCompiler,
    WorkflowRecoveryError,
    compiled_workflow_for_run,
)
from molab.workspace import Workspace  # noqa: E402

_GOLDEN_OK = "drop-harness-01-src: ok"

_DELETED_MODULES = (
    "molab.harness",
    "molab.server.shutdown",
    "molab.workspace.curation",
    "molab.plugins.extras",
    "molab.cli.workspace.mcp_config",
)
_PLUGIN_GROUPS = ("molab.cli_plugins", "molab.server_plugins")
_CORE_PATHS = frozenset(
    {
        "/api/health",
        "/api/workspace/info",
        "/api/workspace/copilot",
        "/api/projects",
        "/api/knowledge/search",
        "/api/projects/{project_id}/experiments/{experiment_id}/runs/{run_id}/executions",
    }
)
_HARNESS_PREFIXES = ("/api/agent", "/api/approvals", "/api/plans")
_HARNESS_FRAGMENTS = ("/plan-tasks", "/plans", "curate")
_HARNESS_VERBS = frozenset({"plan", "agent", "curate", "harness", "mcp"})
_CORE_VERBS = frozenset({"run", "serve", "runs"})


def _check_modules() -> None:
    assert _LOADED_AFTER_IMPORT == [], _LOADED_AFTER_IMPORT
    alive = [name for name in _DELETED_MODULES if importlib.util.find_spec(name) is not None]
    assert alive == [], alive

    for group in _PLUGIN_GROUPS:
        ours = [
            ep.value
            for ep in importlib.metadata.entry_points(group=group)
            if ep.value.startswith("molab.")
        ]
        print(f"{group}: molab-owned entry points {ours}", file=sys.stderr)
        assert ours == [], (group, ours)


def _check_openapi() -> None:
    paths = set(create_app(serve_static=False).openapi()["paths"])
    print(f"openapi: {len(paths)} paths", file=sys.stderr)
    missing = sorted(_CORE_PATHS - paths)
    assert missing == [], missing
    harness = sorted(
        p
        for p in paths
        if p.startswith(_HARNESS_PREFIXES) or any(frag in p for frag in _HARNESS_FRAGMENTS)
    )
    assert harness == [], harness


def _check_cli() -> None:
    command = typer.main.get_command(molab.cli.app)
    names = set(getattr(command, "commands", {}))
    print(f"cli verbs: {sorted(names)}", file=sys.stderr)
    assert names & _HARNESS_VERBS == set(), sorted(names & _HARNESS_VERBS)
    assert names >= _CORE_VERBS, sorted(_CORE_VERBS - names)


def _check_surfaces() -> None:
    assert not hasattr(molab.workflow, "set_workflow_recoverer")
    assert not hasattr(molab.services.operator_config, "bridge_operator_config")
    assert hasattr(molab.services.operator_config, "load_operator_config")
    assert not hasattr(molab.knowledge, "PLAN_BOOK_NAME")


def _check_recovery(ws: Workspace) -> None:
    run = ws.add_project("unbound").add_experiment("bare").add_run(params={"seed": 0})
    try:
        compiled_workflow_for_run(run)
    except WorkflowRecoveryError as exc:
        message = str(exc)
    else:
        raise AssertionError("compiled_workflow_for_run did not raise")
    print(f"recovery error: {message}", file=sys.stderr)
    assert "workflow_entrypoint" in message, message
    assert "molab plan" not in message, message


def _check_script_run(ws: Workspace) -> None:
    wf = Workflow(name="drop-harness-01-one-task")

    @wf.task
    def step(ctx: TaskContext) -> dict[str, bool]:
        del ctx  # the body only has to succeed
        return {"ok": True}

    compiled = WorkflowCompiler().compile(wf)
    experiment = ws.add_project("p").add_experiment("e").define(compiled, params={"seed": [0]})
    [run] = experiment.list_runs()
    run.execute(compiled)
    by_status = dict(run.status_summary.by_status)
    print(f"script run by_status={by_status}", file=sys.stderr)
    assert by_status == {"succeeded": 1}, by_status


def _check(tmp: Path) -> list[str]:
    _check_modules()
    _check_openapi()
    _check_cli()
    _check_surfaces()
    ws = Workspace(tmp / "lab", name="Lab")
    ws.materialize()
    _check_recovery(ws)
    _check_script_run(ws)
    return [_GOLDEN_OK]


def main() -> None:
    saved_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as raw:
        os.environ["GIT_CEILING_DIRECTORIES"] = raw
        os.chdir(raw)
        try:
            lines = _check(Path(raw))
        finally:
            os.chdir(saved_cwd)
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
