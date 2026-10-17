"""molab CLI — flat command tree.

Top-level verbs (``run`` / ``serve`` / ``monitor`` / ``explore`` / ``context`` /
``info`` / ``exec`` / ``shell`` / ``connect`` / ``sync`` / ``push`` / ``pull`` /
``init`` / ``validate``, plus the hidden molq worker entry ``execute``) and
noun groups (``project`` / ``experiment`` /
``runs`` / ``asset`` / ``target`` / ``session`` / ``config`` / ``auth`` /
``git`` / ``knowledge``) register directly on the app. Each
workspace-bound command resolves its execution target via
:mod:`molab.cli._target`. There is no ``workspace`` god-group.
"""

from __future__ import annotations

import contextlib

import typer
from mollog import get_logger

from molab.cli import connect_cmd as _connect_cmd
from molab.cli._app import app

# ── init (top-level command function) ────────────────────────────────────────
from molab.cli.init_cmd import init as _init_cmd

# ── Verbs — self-register on `app` via @app.command when imported ─────────────
from molab.cli.workspace import context as _context
from molab.cli.workspace import explore as _explore
from molab.cli.workspace import lifecycle as _lifecycle
from molab.cli.workspace import monitor as _monitor
from molab.cli.workspace import run as _run
from molab.cli.workspace import serve as _serve
from molab.cli.workspace import sync as _sync

app.command(name="init")(_init_cmd)

# ── Noun groups (resource CRUD) — flat at top level ──────────────────────────
from molab.cli.prune import register as _register_prune  # noqa: E402
from molab.cli.target_cmd import target_app  # noqa: E402
from molab.cli.workspace.resources import (  # noqa: E402
    asset_app,
    experiment_app,
    project_app,
    run_app,
)

_register_prune(run_app)  # add `prune` to the runs group (list / info / prune / …)
app.add_typer(project_app, name="project")
app.add_typer(experiment_app, name="experiment")
app.add_typer(run_app, name="runs")
app.add_typer(asset_app, name="asset")
app.add_typer(target_app, name="target")

# ── git checkpoint projection group ──────────────────────────────────────────
from molab.cli.history_cmd import history_app  # noqa: E402
from molab.cli.migrate_cmd import migrate_app  # noqa: E402

app.add_typer(history_app, name="history")
app.add_typer(migrate_app, name="migrate")

# ── session + config groups ──────────────────────────────────────────────────
from molab.cli.session_cmd import session_app  # noqa: E402

app.add_typer(session_app, name="session")

from molab.cli.config_cmd import config_app  # noqa: E402

app.add_typer(config_app, name="config")

# ── auth (filesystem users + gh-shaped login) ────────────────────────────────
from molab.cli.auth_cmd import auth_app  # noqa: E402

app.add_typer(auth_app, name="auth")

# ── knowledge group (OKF notes + literature) ─────────────────────────────────
from molab.cli.knowledge_cmd import knowledge_app  # noqa: E402

app.add_typer(knowledge_app, name="knowledge")

# ── Third-party CLI plugin discovery ─────────────────────────────────────────
_logger = get_logger(__name__)


def _register_third_party_cli_plugins(app: typer.Typer) -> None:
    from molab.plugins import discover_cli_plugins

    for plugin in discover_cli_plugins():
        try:
            plugin.register(app)
        except Exception as exc:
            _logger.warning(f"plugin '{plugin.id}' register raised; skipping: {exc}")


_register_third_party_cli_plugins(app)
