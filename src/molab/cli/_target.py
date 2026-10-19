"""Shared workspace address resolution and CLI error presentation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from molab.workspace.fs import FileSystem
from molab.workspace.target import (
    Target,
    TargetNeedsResolution,
    TargetNotFound,
    resolve_target,
)

if TYPE_CHECKING:
    from molab.workspace import Workspace

#: Shared ``--workspace/-ws`` option (``-t/--target`` kept as a hidden,
#: back-compatible alias). Defaults to the current directory.
TargetOption = Annotated[
    str,
    typer.Option(
        "--workspace",
        "-ws",
        "--target",
        "-t",
        help="Workspace: a path, cluster:path, or @target-name (default: cwd).",
    ),
]


def resolve_workspace_target(target_str: str = ".") -> tuple[Target, FileSystem]:
    """Resolve a target string into ``(target, fs)``.

    Uses :func:`molab.workspace.target.resolve_target` so commands share one
    local/remote resolution path. ``@name`` targets are looked up in the cwd
    workspace's compute-target registry.

    Args:
        target_str: Target spec; ``"."`` (default) -> local cwd workspace,
            ``cluster:/path`` -> remote, ``@name`` -> registered target.

    Returns:
        ``(resolved_target, filesystem)``.

    Raises:
        typer.Exit: code 1 if the target cannot be resolved, after printing
            the error.
    """
    spec = target_str or "."

    ws = None
    if spec.startswith("@"):
        # ``@name`` needs a workspace to look up the compute-target registry.
        from molab.workspace import Workspace

        try:
            ws = Workspace.load(".")
        except Exception:
            ws = None

    try:
        resolved, fs = resolve_target(spec, ws)
    except (TargetNotFound, TargetNeedsResolution) as exc:
        from molab.cli._common import rprint

        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    return resolved, fs


def open_workspace(
    target_str: str = ".",
    *,
    require_existing: bool = True,
    prefetch: bool = False,
    name: str | None = None,
) -> tuple[Target, FileSystem, Workspace]:
    """Resolve *target_str* and open the Workspace on the matching FileSystem.

    Local and remote targets share this path and explicitly bind their filesystem.
    ``require_existing=True`` (default) fails when ``workspace.json`` is
    missing; pass ``False`` for ``init``-style create.

    Args:
        target_str: Target spec (path, ``cluster:path`` or ``@name``).
        require_existing: Fail when the workspace marker is absent.
        name: Display name used when this call creates the workspace.
        prefetch: Warm the whole navigation tree up front. Commands that are
            about to walk projects/experiments/runs should pass ``True``: on a
            remote workspace that turns a round-trip per node into two for the
            entire tree. Commands that touch one known path should not.

    Raises:
        FileNotFoundError: when *require_existing* and no workspace marker.
        typer.Exit: when the target string cannot be resolved, or a remote
            host needs an interactive 2FA login first.
    """
    from molab.workspace import Workspace
    from molab.workspace.target import RemoteTarget

    target, fs = resolve_workspace_target(target_str)
    root = target.path
    root_str = str(root)

    if require_existing:
        marker = fs.join(root_str, "workspace.json")
        try:
            present = fs.exists(marker)
        except Exception as exc:
            # Surface auth-ish transport errors with a connect hint.
            from molab.cli._common import rprint

            rprint(f"[red]Error:[/red] cannot reach remote workspace: {exc}")
            if isinstance(target, RemoteTarget):
                rprint(
                    f"[dim]If the host needs a verification code (2FA), run: "
                    f"[bold]molab connect -ws {target_str}[/bold], then retry.[/dim]"
                )
            raise typer.Exit(1) from exc
        if not present:
            raise FileNotFoundError(
                f"No workspace found at {root} — run molab init {root} to create one"
            )
    ws = Workspace(root, name=name, fs=fs)
    if prefetch:
        _prefetch_tree(fs, ws)
    return target, fs, ws


def _prefetch_tree(fs: FileSystem, ws: Workspace) -> None:
    """Warm a cached remote filesystem's navigation tree; no-op otherwise.

    Best-effort: a prefetch failure must not stop a command that would work
    (more slowly) without it.
    """
    prepare = getattr(fs, "prepare", None)
    if prepare is None:
        return
    try:
        prepare(ws, block_index=True, refresh_on_open=False)
    except Exception:  # warming is an optimisation, never a gate
        import logging

        logging.getLogger(__name__).debug("remote prefetch failed; continuing", exc_info=True)
