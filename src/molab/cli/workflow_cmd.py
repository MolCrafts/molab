"""``molab workflow dry-run`` — what a script would run, without writing anything.

``molab run`` imports a script to discover its workspaces, and the script's
``exp.define(wf, params=...)`` seeds runs and binds the workflow as it goes.
The preview imports the script the same way (:func:`molab.entry.load_workspaces`),
but under a scratch root — the ``set_cli_root_override(..., explicit=True)``
seam ``molab run -ws`` uses — so every record the import creates lands in a
temporary directory that is deleted afterwards. The real workspace is never
addressed: no run, no execution, no index is written there. Each bound
workflow is then walked with :func:`molab.workflow.dry_run.simulate`.

The experiment's real id is looked up by its path under the workspace root
``molab run`` would use (``-ws``, else the script's directory); ``null`` means
``molab run`` would create it.
"""

from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from molab.cli._common import rprint
from molab.cli._target import TargetOption, resolve_workspace_target

if TYPE_CHECKING:
    from molab._typing import JSONValue

workflow_app = typer.Typer(help="Workflow previews", no_args_is_help=True)


def _root_for(script: Path, target_spec: str) -> Path:
    """The workspace root ``molab run`` would use for *script*."""
    from molab.entry import infer_workspace_root
    from molab.workspace.target import LocalTarget

    target, _fs = resolve_workspace_target(target_spec)
    if not isinstance(target, LocalTarget):
        rprint("[red]Error:[/red] `molab workflow dry-run` previews a local workspace root.")
        raise typer.Exit(1)
    if target_spec != ".":
        return Path(target.path).resolve()
    try:
        return infer_workspace_root(script)
    except ValueError:
        return Path.cwd().resolve()


def _existing_experiment_id(root: Path, rel_path: str) -> str | None:
    """The id of the experiment recorded at ``root/rel_path``, or ``None``."""
    from molab import frontmatter
    from molab.fs import LocalFS
    from molab.workspace.entity_record import INDEX_FILENAME
    from molab.workspace.folder import WORKSPACE_EXPERIMENT_KIND

    head = frontmatter.read_head(LocalFS(), root / rel_path / INDEX_FILENAME)
    if not head or head.get("type") != WORKSPACE_EXPERIMENT_KIND:
        return None
    found = head.get("id")
    return found if isinstance(found, str) else None


def _preview(script: Path, root: Path) -> list[dict[str, JSONValue]]:
    """Import *script* under a scratch root and report every bound experiment."""
    from molab.entry import load_workspaces
    from molab.workflow import default_binding_registry
    from molab.workflow.dry_run import report_from_compiled
    from molab.workspace.workspace import set_cli_root_override

    reports: list[dict[str, JSONValue]] = []
    with tempfile.TemporaryDirectory(prefix="molab-dry-run-") as scratch:
        set_cli_root_override(scratch, explicit=True)
        try:
            workspaces = load_workspaces(script)
        except Exception as exc:
            rprint(f"[red]Error importing {script.name}:[/red] {exc}")
            rprint(traceback.format_exc(), end="")
            raise typer.Exit(1) from None
        finally:
            set_cli_root_override(None)
        for ws in workspaces:
            for project in ws.list_projects():
                for exp in project.list_experiments():
                    compiled = default_binding_registry.for_experiment(exp)
                    if compiled is None:
                        continue
                    rel_path = Path(str(exp.resolve())).relative_to(Path(str(ws.root))).as_posix()
                    reports.append(
                        report_from_compiled(
                            compiled,
                            experiment={
                                "id": _existing_experiment_id(root, rel_path),
                                "name": exp.metadata.name,
                                "path": rel_path,
                            },
                            runs=[run.parameters for run in exp.declared_runs()],
                        )
                    )
                    default_binding_registry.unbind(exp)
    if not workspaces:
        rprint(
            "[red]Error:[/red] No me.entry() call found in script. "
            "Add [bold]me.entry(workspace)[/bold] at module level."
        )
        raise typer.Exit(1)
    return reports


def _rows(report: dict[str, JSONValue], key: str) -> list[dict[str, JSONValue]]:
    """The object rows under *key* of a dry-run document."""
    rows = report[key]
    assert isinstance(rows, list)
    return [row for row in rows if isinstance(row, dict)]


def _names(value: JSONValue) -> str:
    assert isinstance(value, list)
    return ", ".join(str(name) for name in value)


def _print_report(report: dict[str, JSONValue]) -> None:
    experiment = report["experiment"]
    workflow = report["workflow"]
    assert isinstance(experiment, dict) and isinstance(workflow, dict)
    existing = experiment["id"]
    where = f"id {existing}" if existing else "not created yet"
    rprint(f"\n[bold]Experiment:[/bold] {experiment['name']}  ({experiment['path']}, {where})")
    rprint(f"  Workflow:  {workflow['name']}")
    rprint("  Tasks:")
    for task in _rows(report, "tasks"):
        suffix = f"  <- {_names(task['depends_on'])}" if task["depends_on"] else ""
        rprint(f"    {task['name']}{suffix}")
    rprint("  Waves:")
    waves = report["waves"]
    assert isinstance(waves, list)
    for position, wave in enumerate(waves, start=1):
        rprint(f"    {position}. {_names(wave)}")
    branches = _rows(report, "branches")
    if branches:
        rprint("  Branches:")
        for branch in branches:
            rprint(f"    {branch['source']} --{branch['label']}--> {branch['target']}")
    else:
        rprint("  Branches: (none)")
    runs = _rows(report, "runs")
    rprint(f"  Runs ({len(runs)}):")
    for run in runs:
        rprint(f"    {json.dumps(run['params'], ensure_ascii=False, sort_keys=True)}")


@workflow_app.command("dry-run")
def workflow_dry_run(
    script: Annotated[
        Path,
        typer.Argument(
            help="Python script with me.entry(ws) call.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Print one JSON object per bound experiment, one per line."),
    ] = False,
    target_spec: TargetOption = ".",
) -> None:
    """Preview what `molab run SCRIPT` would do, writing nothing.

    Imports the script as `molab run` does, under a throwaway root, and
    prints per bound experiment: the workflow, its tasks and their
    dependencies, the task waves in order, the declared branches and the run
    parameter sets the script declares. Exits 1 when the script does not
    import or a workflow does not compile.
    """
    root = _root_for(script, target_spec)
    reports = _preview(script, root)
    if json_out:
        for report in reports:
            print(json.dumps(report, ensure_ascii=False))
        return
    if not reports:
        rprint("[dim]No bound experiments found.[/dim]")
        return
    for report in reports:
        _print_report(report)
    rprint(f"\n[green]OK[/green] dry run: {len(reports)} experiment(s), nothing written.")
