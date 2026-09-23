"""``molab context`` — print the canonical WorkspaceContext read-model.

The CLI consumes the **same** projection the server ``GET /context`` route
does — ``molab.services.knowledge_context.context_with_knowledge`` assembles the
complete read-model (knowledge included), so Python and UI operations share one
backend code path and the CLI defines no projection of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from molab.cli._app import app
from molab.cli._common import rprint
from molab.cli._target import TargetOption, open_workspace

if TYPE_CHECKING:
    from molab.workspace.workspace_context import WorkspaceContext


@app.command()
def context(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Focus project id.")
    ] = None,
    experiment: Annotated[
        str | None, typer.Option("--experiment", "-e", help="Focus experiment id.")
    ] = None,
    run: Annotated[str | None, typer.Option("--run", help="Focus run id.")] = None,
    target_spec: TargetOption = ".",
) -> None:
    """Print the workspace's canonical structural read-model (WorkspaceContext)."""
    from molab.services.knowledge_context import context_with_knowledge
    from molab.workspace import ContextFocus

    try:
        _target, _transport, _fs, ws = open_workspace(target_spec, prefetch=True)
    except FileNotFoundError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        rprint("  Run [bold]molab init[/bold] to create one.")
        raise typer.Exit(1) from exc

    focus = ContextFocus(project_id=project, experiment_id=experiment, run_id=run)
    _render(context_with_knowledge(ws, focus=focus))


def _render(ctx: WorkspaceContext) -> None:
    """Render *ctx* as a structured summary; missing state renders as explicit none."""
    rprint(f"[bold]{ctx.workspace.name}[/bold]  [dim]{ctx.workspace.root}[/dim]")
    rprint(f"  projects:    {len(ctx.projects)}")
    rprint(f"  experiments: {len(ctx.experiments)}")
    rprint(f"  workflows:   {len(ctx.workflows)}")
    rprint(f"  artifacts:   {len(ctx.artifacts)}")
    rprint(f"  knowledge:   {len(ctx.knowledge)}")
    rprint(
        f"  runs:        {len(ctx.recent_runs)} "
        f"([green]{len(ctx.running_runs)} running[/green], "
        f"[red]{len(ctx.failed_runs)} failed[/red])"
    )

    if ctx.recent_runs:
        rprint("  recent runs:")
        for ref in ctx.recent_runs[:10]:
            rprint(f"    - {ref.run_id}  [{ref.status}]  exp={ref.experiment_id}")
    else:
        rprint("  recent runs: [dim]none[/dim]")

    if ctx.stale_or_missing:
        rprint("  [yellow]health flags:[/yellow]")
        for flag in ctx.stale_or_missing:
            rprint(f"    - {flag.kind}: {flag.detail}")
    else:
        rprint("  health flags: [dim]none[/dim]")
