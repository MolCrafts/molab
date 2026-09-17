"""The harness's own HTTP surface, mounted into a molab server process.

molab discovers this through the ``molab.server_plugins`` entry-point group
(:mod:`molab.plugins.server`), so the routers, the background-task registries
and their lifespan teardown all live here — molab itself never names them.

Same process, same port, same session cookie as the rest of ``/api``: the
harness frontend is a UI plugin on the same origin, and ``pip install molab``
still starts a server without one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.plugins.server import ServerPlugin

if TYPE_CHECKING:
    from fastapi import APIRouter

__all__ = ["SERVER_PLUGIN", "register", "shutdown", "signal_shutdown", "startup"]


def register(router: APIRouter) -> None:
    """Attach the harness routers to the gated ``/api`` router.

    ``agent_admin`` MUST precede ``agent``: both mount under ``/agent`` and
    ``agent.router`` ends in a legacy 503 catch-all, so registration order
    decides which wins — the real provider / MCP routes have to come first.
    """
    # Imported here, not at module import, so merely *discovering* the plugin
    # does not drag the whole harness into a process that will not serve it.
    from molab.harness.server.routes import (
        agent,
        agent_admin,
        agent_tasks,
        approvals,
        curate_tasks,
        curate_workspace,
        plan_tasks,
        plans,
    )

    router.include_router(agent_admin.router)
    router.include_router(agent.router)
    router.include_router(agent_tasks.router)
    router.include_router(approvals.router)
    router.include_router(curate_tasks.router)
    router.include_router(plan_tasks.router)
    router.include_router(plans.router)
    router.include_router(plans.flat_router)
    router.include_router(curate_workspace.router)


def startup() -> None:
    """Arm the approval pub/sub and the generated-workflow recovery seam."""
    # Importing this module registers the plan-generated workflow recoverer on
    # ``molab.workflow``'s seam, so `molab run` can execute a plan-made run.
    import molab.harness.workflow_recovery
    from molab.harness.services.approval_notify import reset_approval_subscribers

    reset_approval_subscribers()


def signal_shutdown() -> None:
    """Wake the approvals SSE long-pollers so connection drain can finish."""
    from molab.harness.services.approval_notify import close_approval_subscribers

    close_approval_subscribers()


async def shutdown() -> None:
    """Cancel and await every in-flight agent turn / plan task / curate task."""
    from molab.harness.server.deps.agent_runtime import reset_agent_runtime
    from molab.harness.server.deps.curate_runtime import reset_curate_runtime
    from molab.harness.server.deps.plan_runtime import reset_plan_runtime

    await reset_agent_runtime()
    await reset_plan_runtime()
    await reset_curate_runtime()


SERVER_PLUGIN = ServerPlugin(
    id="harness",
    name="molab harness",
    version="1",
    register=register,
    startup=startup,
    signal_shutdown=signal_shutdown,
    shutdown=shutdown,
)
