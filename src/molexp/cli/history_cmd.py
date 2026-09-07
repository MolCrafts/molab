"""``molexp history {log,sync,push}`` — the workspace's git history.

A molexp workspace is a git repository: entity files are the truth, and each
mutation is committed with the provenance fact in its message trailers. These
commands are the thin CLI surface over :class:`molexp.workspace.GitHistory`,
which the server's ``/api/history/*`` routes also call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from molexp.cli._common import get_workspace, rprint
from molexp.cli._target import TargetOption, resolve_workspace_target
from molexp.workspace.history import GitHistory
from molexp.workspace.target import LocalTarget

history_app = typer.Typer(help="Workspace history (git)", no_args_is_help=True)


def _remote_only(verb: str) -> NoReturn:
    rprint(f"[red]Error:[/red] `molexp history {verb}` only supports a local workspace.")
    raise typer.Exit(1)


def _history(target_spec: str) -> GitHistory:
    target, _transport, _fs = resolve_workspace_target(target_spec)
    if not isinstance(target, LocalTarget):
        _remote_only("history")
    ws = get_workspace(target.path if target.path != Path.cwd() else None)
    return GitHistory(ws.root)


@history_app.command("log")
def history_log(
    entity: Annotated[str | None, typer.Option(help="Narrow to one entity id")] = None,
    event: Annotated[str | None, typer.Option(help="Narrow to one event type")] = None,
    limit: Annotated[int, typer.Option(help="Maximum facts to show")] = 20,
    target_spec: TargetOption = ".",
) -> None:
    """Show what happened, newest first."""
    history = _history(target_spec)
    if not history.enabled():
        rprint("[yellow]No history[/yellow] — run `molexp history init` first.")
        raise typer.Exit(1)
    entries = history.entries(entity_id=entity, event=event, limit=limit)
    if not entries:
        rprint("[dim]no matching facts[/dim]")
        return
    for item in entries:
        when = item.occurred_at.strftime("%Y-%m-%d %H:%M")
        rprint(f"[dim]{item.commit[:8]}[/dim] {when}  [cyan]{item.event}[/cyan]  {item.summary}")


@history_app.command("init")
def history_init(target_spec: TargetOption = ".") -> None:
    """Make the workspace a git repository (idempotent)."""
    history = _history(target_spec)
    if not history.init():
        rprint("[red]Error:[/red] git is not available on PATH.")
        raise typer.Exit(1)
    rprint(f"[green]OK[/green] history at {history.git_dir}")


@history_app.command("sync")
def history_sync(target_spec: TargetOption = ".") -> None:
    """Commit anything a worker left uncommitted."""
    history = _history(target_spec)
    commit = history.sweep()
    if commit is None:
        rprint("[dim]nothing to record[/dim]")
        return
    rprint(f"[green]OK[/green] recorded {commit[:8]}")


@history_app.command("push")
def history_push(
    remote: Annotated[str, typer.Argument(help="Git remote URL or path")],
    target_spec: TargetOption = ".",
) -> None:
    """Push the workspace history to a remote — this is the backup."""
    history = _history(target_spec)
    history.sweep()
    proc = subprocess.run(
        ["git", "push", remote, "HEAD"],
        cwd=history.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        rprint(f"[red]Error:[/red] {proc.stderr.strip()}")
        raise typer.Exit(1)
    rprint(f"[green]OK[/green] pushed → {remote}")
