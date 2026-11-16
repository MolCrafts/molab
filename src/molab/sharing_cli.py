"""Isolated sharing launcher; does not load the plugin-discovering molab CLI."""

from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from molab.sharing.settings import GatewaySettings, WorkerSettings, read_private_config
from molab.sharing.store import SharingStore

app = typer.Typer(
    no_args_is_help=True,
    help="HPC Project metadata sharing, with fixed user identities.",
    pretty_exceptions_show_locals=False,
)


def _store(config: Path) -> SharingStore:
    settings = GatewaySettings.model_validate_json(read_private_config(config))
    return SharingStore(settings.state_dir, local_state_confirmed=settings.local_state_confirmed)


@app.command()
def gateway(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8080,
    uds: Annotated[
        Path | None, typer.Option(help="Site-managed Unix socket instead of loopback TCP.")
    ] = None,
) -> None:
    """Serve shared metadata behind the cluster's authenticated reverse proxy."""
    from molab.server.sharing import create_sharing_app

    settings = GatewaySettings.model_validate_json(read_private_config(config))
    web = Path(str(resources.files("molab") / "dist"))
    application = create_sharing_app(
        settings, static_dir=web if (web / "index.html").is_file() else None
    )
    uvicorn.run(
        application, host="127.0.0.1", port=port, uds=str(uds) if uds else None, proxy_headers=False
    )


@app.command()
def worker(
    root: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8081,
    uds: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Serve only as this process's UID. Launch separately for each user."""
    from molab.server.sharing_worker import create_managed_app

    settings = WorkerSettings.model_validate_json(read_private_config(config))
    web = Path(str(resources.files("molab") / "dist"))
    application = create_managed_app(
        root, settings, static_dir=web if (web / "index.html").is_file() else None
    )
    uvicorn.run(
        application, host="127.0.0.1", port=port, uds=str(uds) if uds else None, proxy_headers=False
    )


@app.command("principal-add")
def principal_add(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    issuer: Annotated[str, typer.Option()],
    subject: Annotated[str, typer.Option()],
    name: Annotated[str, typer.Option()],
) -> None:
    """Provision a stable trusted identity as the gateway operator."""
    settings = GatewaySettings.model_validate_json(read_private_config(config))
    if issuer != settings.issuer:
        raise typer.BadParameter("issuer must match the configured authentication provider")
    typer.echo(_store(config).provision_principal(issuer, subject, name).model_dump_json())


@app.command("source-add")
def source_add(
    config: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    principal: Annotated[str, typer.Option()],
    cluster: Annotated[str, typer.Option()],
    uid: Annotated[int, typer.Option(min=1)],
    credential_file: Annotated[
        Path, typer.Option(help="New private file; token is never printed.")
    ],
) -> None:
    """Bind a user service to a Principal, cluster, and non-root UID."""
    store = _store(config)
    try:
        descriptor = os.open(
            credential_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
    except FileExistsError as exc:
        raise typer.BadParameter("credential file must not already exist") from exc
    source_id: str | None = None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            source_id, token = store.provision_source(principal, cluster, uid)
            handle.write(json.dumps({"source_id": source_id, "source_token": token}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        credential_file.unlink(missing_ok=True)
        if source_id is not None:
            store.disable_source(source_id)
        raise
    typer.echo(f"Created source {source_id}; credential written to {credential_file}")


@app.command("principal-disable")
def principal_disable(config: Annotated[Path, typer.Option(exists=True)], principal: str) -> None:
    """Disable sharing access without recycling the stable identity."""
    _store(config).disable_principal(principal)


@app.command("source-disable")
def source_disable(config: Annotated[Path, typer.Option(exists=True)], source: str) -> None:
    """Revoke a publisher credential without borrowing its Linux identity."""
    _store(config).disable_source(source)


if __name__ == "__main__":
    app()
