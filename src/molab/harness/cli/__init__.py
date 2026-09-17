"""The harness's own CLI commands, attached to a molab Typer app.

molab discovers this through the ``molab.cli_plugins`` entry-point group
(:mod:`molab.plugins.cli`), so ``molab plan`` / ``molab curate`` /
``molab agent`` exist exactly when the harness is installed — molab's own
command tree never names them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.plugins.cli import CliPlugin

if TYPE_CHECKING:
    import typer

__all__ = ["CLI_PLUGIN", "register"]


def register(app: typer.Typer) -> None:
    """Attach the harness verbs to *app*.

    Everything the harness contributes hangs off *app* directly. It never
    reaches into another package's command tree: a plugin that has to import
    ``molab.cli.config_cmd`` to graft a subcommand onto molab's ``config``
    group is not using a seam, it is editing its host.
    """
    # Imported here, not at module import, so discovering the plugin does not
    # drag the harness (and its agent stack) into every `molab --help`.
    from molab.harness.cli.agent_cmd import agent_app
    from molab.harness.cli.config_dump import harness_app
    from molab.harness.cli.curate_cmd import curate_app
    from molab.harness.cli.plan_cmd import plan

    app.add_typer(agent_app, name="agent")
    app.command(name="plan")(plan)
    app.add_typer(curate_app, name="curate")
    app.add_typer(harness_app, name="harness")

    # Registers the plan-generated workflow recoverer on ``molab.workflow``'s
    # seam, so `molab run` / `molab runs resume` can execute a plan-made run
    # in this process.
    import molab.harness.workflow_recovery


CLI_PLUGIN = CliPlugin(
    id="harness",
    name="molab harness",
    version="1",
    register=register,
)
