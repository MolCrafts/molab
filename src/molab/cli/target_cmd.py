"""``molab target`` — list/add/remove/test compute-target registry.

Compute targets live on ``WorkspaceMetadata.targets`` as immutable
:class:`molab.workspace.models.ComputeTarget` records.  This CLI is a
thin user-facing wrapper around the CRUD helpers in
:mod:`molab.workspace.targets`.

Each subcommand is fully workspace-rooted via the ``--path`` option,
because the registry is per-workspace state.  No global registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from molab.cli._common import rprint

target_app = typer.Typer(
    name="target",
    help="Manage compute targets (list / add / remove / test).",
    no_args_is_help=True,
)


def _open_workspace(path: Path):
    """Load the workspace at *path*, exiting 1 with a helpful message on failure."""
    from molab.workspace import Workspace

    try:
        return Workspace.load(path)
    except Exception as exc:
        rprint(f"[red]Failed to open workspace at {path}:[/red] {exc}")
        raise typer.Exit(1) from exc


@target_app.command("list")
def list_cmd(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Workspace path"),
    ],
) -> None:
    """List all registered compute targets."""
    from molab.workspace.targets import list_targets

    ws = _open_workspace(path)
    targets = list_targets(ws)
    if not targets:
        rprint("[dim]No compute targets registered.[/dim]")
        return
    for t in targets:
        destination = t.cluster_id or "(local)"
        rprint(f"  [bold]{t.name}[/bold]  destination={destination}  scratch={t.scratch_root}")


@target_app.command("add")
def add_cmd(
    name: Annotated[str, typer.Argument(help="Target name (must be unique)")],
    scratch: Annotated[
        str, typer.Option("--scratch", help="Scratch root on the target's filesystem")
    ],
    cluster: Annotated[
        str, typer.Option("--cluster", help="Registered molq destination name or ID")
    ],
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Workspace path"),
    ] = Path.cwd(),
) -> None:
    """Register a new compute target on the workspace."""
    from molab.workspace.models import ComputeTarget
    from molab.workspace.targets import add_target

    ws = _open_workspace(path)
    from molab.workspace.connection import get_client

    client = get_client()
    definition = client.cluster(cluster).definition()
    target = ComputeTarget(
        name=name,
        registry_id=client.rpc("molq.hello")["registry_id"],
        cluster_id=definition["id"],
        scratch_root=scratch,
    )
    try:
        add_target(ws, target)
    except ValueError as exc:
        # already exists → exit 1 per tests
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    rprint(
        f"[green]OK[/green] Added target {name}  destination={definition['name']}  scratch={scratch}"
    )


@target_app.command("remove")
def remove_cmd(
    name: Annotated[str, typer.Argument(help="Target name to remove")],
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Workspace path"),
    ] = Path.cwd(),
) -> None:
    """Remove a compute target from the workspace registry."""
    from molab.workspace.targets import remove_target

    ws = _open_workspace(path)
    try:
        remove_target(ws, name)
    except KeyError as exc:
        rprint(f"[red]No target named {name!r}[/red]")
        raise typer.Exit(1) from exc

    rprint(f"[green]OK[/green] Removed target {name}")


@target_app.command("test")
def test_cmd(
    name: Annotated[str, typer.Argument(help="Target name to probe")],
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Workspace path"),
    ] = Path.cwd(),
) -> None:
    """Check destination access with a file round trip under its scratch root."""
    import uuid

    from molab.workspace.targets import get_target, to_filesystem

    ws = _open_workspace(path)
    try:
        target = get_target(ws, name)
        fs = to_filesystem(target)
        fs.mkdir(target.scratch_root, parents=True, exist_ok=True)
        probe = fs.join(target.scratch_root, f".molab-probe-{uuid.uuid4().hex}")
        try:
            fs.write_text(probe, "molab target probe\n")
            if fs.read_text(probe) != "molab target probe\n":
                raise OSError("File round-trip payload mismatch")
        finally:
            fs.remove(probe)
    except (KeyError, ValueError, OSError) as exc:
        rprint(f"[red]Target check failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    rprint("[green]ok file round-trip[/green]")
