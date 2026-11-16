"""Authenticate a registered molq destination with one response."""

from __future__ import annotations

import typer

from molab.cli._app import app
from molab.cli._common import rprint
from molab.cli._target import TargetOption, resolve_workspace_target
from molab.workspace.target import RemoteTarget


@app.command("connect")
def connect(target_spec: TargetOption = ".") -> None:
    target, _ = resolve_workspace_target(target_spec)
    if not isinstance(target, RemoteTarget):
        return
    from molab.workspace.connection import get_client

    code = typer.prompt("Verification code", hide_input=True)
    get_client(target.registry_id).cluster(target.cluster_id).authenticate(code)
    rprint("[green]Connected[/green]")
