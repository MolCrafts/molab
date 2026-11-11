"""``molab check {path,command,tree}`` — the questions an agent hook asks (D91).

The molcrafts-harness hooks hold no layout rule: they forward each file write
to ``molab check path``, each shell command to ``molab check command``, and
each session start / stop to ``molab check tree``, and act on the JSON verdict.
These commands exit 0 whenever molab itself worked; the verdict's ``allowed``
decides. The rules live in :mod:`molab.services.workspace_check`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from molab.cli._common import rprint

check_app = typer.Typer(
    help="Ask whether a write, a shell command, or the tree keeps the workspace legal (agent hooks).",
    no_args_is_help=True,
)


def _emit(verdict: object, json_out: bool) -> None:
    from molab.services.workspace_check import Verdict

    assert isinstance(verdict, Verdict)
    if json_out:
        print(json.dumps(verdict.model_dump(mode="json"), ensure_ascii=False))
        return
    if not verdict.in_workspace:
        rprint(f"[dim]{verdict.reason}[/dim]")
        return
    label = "[green]allowed[/green]" if verdict.allowed else "[red]refused[/red]"
    rprint(f"{label} {verdict.path or ''}".rstrip())
    if verdict.reason:
        rprint(f"  {verdict.reason}")
    if verdict.command:
        rprint(f"  use: {verdict.command}")
    for issue in verdict.issues:
        rprint(f"  {issue.severity} {issue.rule} — {issue.path}")


@check_app.command("path")
def check_path(
    path: Annotated[str, typer.Argument(help="The file about to be written or edited.")],
    op: Annotated[str, typer.Option("--op", help="write or edit.")] = "write",
    content_file: Annotated[
        Path | None,
        typer.Option("--content-file", help="A file holding the full content after the change."),
    ] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Print the verdict as JSON.")] = False,
) -> None:
    """Would this write keep the workspace legal? Refusals name the molab command to use."""
    from molab.services.workspace_check import check_path as _check

    if op not in ("write", "edit"):
        rprint(f"[red]Error:[/red] --op must be write or edit, got {op!r}")
        raise typer.Exit(2)
    content = None
    if content_file is not None:
        try:
            content = content_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            rprint(f"[red]Error:[/red] cannot read --content-file: {exc}")
            raise typer.Exit(1) from None
    _emit(_check(path, op, content), json_out)


@check_app.command("command")
def check_command_cmd(
    command: Annotated[
        str, typer.Option("--command", help="The shell command. It is not executed.")
    ],
    cwd: Annotated[
        str, typer.Option("--cwd", help="The directory the command would run in.")
    ] = ".",
    json_out: Annotated[bool, typer.Option("--json", help="Print the verdict as JSON.")] = False,
) -> None:
    """Would the files this command writes keep the workspace legal?"""
    from molab.services.workspace_check import check_command as _check

    _emit(_check(command, cwd), json_out)


@check_app.command("tree")
def check_tree(
    directory: Annotated[str, typer.Argument(help="Any directory inside the workspace.")] = ".",
    snapshot: Annotated[
        str | None,
        typer.Option("--snapshot", help="Record the current errors under this name."),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Report only errors the named snapshot did not have."),
    ] = None,
    new_only: Annotated[
        bool,
        typer.Option("--new-only", help="Report only errors the workspace baseline did not have."),
    ] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Print the verdict as JSON.")] = False,
) -> None:
    """Check the enclosing workspace, whole or against a snapshot."""
    from molab.services.workspace_check import check_tree as _check

    chosen = sum((snapshot is not None, since is not None, new_only))
    if chosen > 1:
        rprint("[red]Error:[/red] pass at most one of --snapshot, --since, --new-only")
        raise typer.Exit(2)
    _emit(_check(directory, since=since, snapshot=snapshot, new_only=new_only), json_out)
