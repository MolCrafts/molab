"""``molab agents sync`` — write the workspace's guide for coding agents.

The managed block of the root ``AGENTS.md`` is rendered from code
(:mod:`molab.services.agent_guide`); ``CLAUDE.md`` gets a ``@AGENTS.md`` line;
the missing managed ``.gitignore`` rules are appended; the validation baseline
is written when absent. Idempotent. ``molab init`` runs it last.
"""

from __future__ import annotations

import typer

from molab.cli._common import rprint
from molab.cli._target import TargetOption, open_workspace

agents_app = typer.Typer(help="The workspace's guide for coding agents", no_args_is_help=True)


@agents_app.command("sync")
def agents_sync(target_spec: TargetOption = ".") -> None:
    """Write the AGENTS.md block, the CLAUDE.md import, ignore rules and the baseline."""
    from molab.services.agent_guide import sync_agent_files

    _target, _fs, ws = open_workspace(target_spec)
    try:
        result = sync_agent_files(ws)
    except NotImplementedError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None
    changed = [
        name
        for name, flag in (
            ("AGENTS.md", result.agents_written),
            ("CLAUDE.md", result.claude_written),
            (".gitignore", bool(result.ignore_rules_added)),
            (".molab/validate-baseline.json", result.baseline_written),
        )
        if flag
    ]
    if changed:
        rprint(f"[green]OK[/green] agents sync {ws.root}: wrote {', '.join(changed)}")
    else:
        rprint(f"[green]OK[/green] agents sync {ws.root}: up to date")
