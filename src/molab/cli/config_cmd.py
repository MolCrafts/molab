"""``molab config`` — global molab configuration."""

from __future__ import annotations

import contextlib
import json
from typing import Annotated

import typer

from molab.cli._common import rprint

# Single source of truth for the operator config path, loader and writer. The
# loader is shared with the server and molab.services.auth (the server must
# not import molab.cli, so it lives in molab.services.operator_config); the
# writer is CLI-only — the server only reads the file.
from molab.services.operator_config import (
    OPERATOR_CONFIG_PATH as _CONFIG_PATH,
)
from molab.services.operator_config import (
    load_operator_config as _load_operator_config,
)
from molab.services.operator_config import (
    set_operator_values as _set_operator_values,
)

config_app = typer.Typer(
    name="config",
    help="Manage global molab configuration.",
    no_args_is_help=True,
)


def _load_config() -> dict:
    return _load_operator_config(_CONFIG_PATH)


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    cfg = _load_config()
    if not cfg:
        rprint(f"[dim]No configuration set.[/dim] ({_CONFIG_PATH} - config path)")
        return

    rprint(f"[bold]Config:[/bold] {_CONFIG_PATH}")
    from rich import print as _rprint

    _rprint(json.dumps(cfg, indent=2))


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key (dot-notation supported).")],
    value: Annotated[str, typer.Argument(help="Value to set.")],
) -> None:
    """Set a configuration value.

    Examples::

        molab config set tunnel.via zrok
        molab config set tunnel.token <token>
        molab config set section.key value
    """
    # Coerce value
    coerced: str | int | float | bool = value
    if value.lower() == "true":
        coerced = True
    elif value.lower() == "false":
        coerced = False
    else:
        try:
            coerced = int(value)
        except ValueError:
            with contextlib.suppress(ValueError):
                coerced = float(value)

    # One writer with the server's Settings PUT: the shared service applies
    # the dotted key and saves atomically (temp + rename, mode 0600).
    _set_operator_values({key: coerced}, path=_CONFIG_PATH)
    rprint(f"[green]OK[/green] Set {key} = {coerced!r}")


@config_app.command("unset")
def config_unset(
    key: Annotated[str, typer.Argument(help="Config key to remove (dot-notation).")],
) -> None:
    """Remove a configuration value."""
    cfg = _load_config()
    parts = key.split(".")
    node = cfg
    for part in parts[:-1]:
        if part not in node:
            rprint(f"[yellow]Key not found:[/yellow] {key}")
            return
        node = node[part]
    if parts[-1] not in node:
        rprint(f"[yellow]Key not found:[/yellow] {key}")
        return
    _set_operator_values({}, unset=[key], path=_CONFIG_PATH)
    rprint(f"[green]OK[/green] Removed {key}")
