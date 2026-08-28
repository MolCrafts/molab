"""Shared top-level Typer app instance.

Defined in its own module so command modules can register on it via
``@app.command(...)`` without importing :mod:`molexp.cli` (which imports them
back — a cycle). :mod:`molexp.cli` assembles the final flat command tree.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="molexp",
    help="Agent-assisted scientific-workflow platform for FAIR research",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        import molexp

        typer.echo(f"molexp {molexp.__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the molexp version and exit.",
    ),
) -> None:
    """Agent-assisted scientific-workflow platform for FAIR research."""
