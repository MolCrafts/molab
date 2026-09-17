"""``molab harness dump-config`` — print the plugin tree a profile boots.

Harness introspection, not operator configuration: it composes a profile's
Host and prints ``Host.dump_config()``. It used to be spelled
``molab config dump`` — grafted onto molab's ``config`` group — but reaching
into another package's command tree is not a plugin seam, and the command
never read operator config in the first place. The harness registers its own
group instead.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from molab.cli._common import rprint

__all__ = ["config_dump", "harness_app"]


harness_app = typer.Typer(
    help="Harness introspection (the agent product's own commands).",
    no_args_is_help=True,
)


@harness_app.command("dump-config")
def config_dump(
    profile: Annotated[
        str,
        typer.Option("--profile", help="Plugin profile: chat | plan | run | curate."),
    ] = "run",
) -> None:
    """Print the plugin tree this profile would boot (not operator config)."""
    import tempfile
    from pathlib import Path
    from typing import cast

    from molab.harness.gateways.gateway import AgentGateway
    from molab.harness.host import (
        compose_chat,
        compose_curate,
        compose_plan,
        compose_run,
    )
    from molab.plugins.extras import default_science_extras

    class _DumpGateway:
        async def call(self, spec: object, *, runtime: object | None = None) -> object:
            del spec, runtime
            raise RuntimeError("config dump does not call the model")

    scratch = Path(tempfile.mkdtemp(prefix="molab-dump-"))
    name = profile.strip().lower()
    dump_gw = cast(AgentGateway, _DumpGateway())
    extras = default_science_extras()
    if name == "chat":
        host = compose_chat(gateway=dump_gw, scratch_dir=scratch)
    elif name == "plan":
        host = compose_plan(run_id="dump", run_dir=scratch, gateway=dump_gw, extra=extras)
    elif name == "curate":
        host = compose_curate(run_id="dump", run_dir=scratch, workspace_root=scratch)
    elif name == "run":
        host = compose_run(run_id="dump", run_dir=scratch, extra=extras)
    else:
        rprint(f"[red]Unknown profile:[/red] {profile!r}. Use chat, plan, run, or curate.")
        raise typer.Exit(1)
    try:
        from rich import print as _rprint

        _rprint(json.dumps(host.dump_config(), indent=2))
    finally:
        host.unload()
