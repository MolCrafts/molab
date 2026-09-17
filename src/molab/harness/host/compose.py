"""Profile composers — named plugin stacks on a :class:`Host`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from molab.harness.host.host import Host
from molab.harness.host.plugins.agent_call import AgentCallPlugin
from molab.harness.host.plugins.approval import ApprovalPlugin
from molab.harness.host.plugins.capabilities import CapabilitiesPlugin
from molab.harness.host.plugins.executor import ExecutorPlugin
from molab.harness.host.plugins.stores import RunStoresPlugin
from molab.harness.host.plugins.tools import ToolsPlugin
from molab.harness.host.plugins.workflow import WorkflowPlugin

if TYPE_CHECKING:
    from molab.harness.executors import Executor
    from molab.harness.gateways.gateway import AgentGateway
    from molab.harness.host.plugin import Plugin
    from molab.harness.registry.capability_registry import CapabilityRegistry
    from molab.workspace.execution_context import ExecutionContext

__all__ = ["compose_chat", "compose_curate", "compose_plan", "compose_run"]


def _mount_extra(host: Host, extra: tuple[Plugin, ...]) -> None:
    for plugin in extra:
        host.mount(plugin)


def compose_chat(
    *,
    gateway: AgentGateway,
    scratch_dir: Path,
    extra: tuple[Plugin, ...] = (),
) -> Host:
    """Chat profile: scratch stores + tools belt + AgentCall."""
    host = Host()
    host.mount(
        RunStoresPlugin(
            run_id="chat",
            run_dir=Path(scratch_dir),
            workspace_root=Path(scratch_dir),
        )
    )
    host.mount(ToolsPlugin())
    host.mount(AgentCallPlugin(gateway))
    _mount_extra(host, extra)
    return host


def compose_plan(
    *,
    run_id: str,
    run_dir: Path,
    gateway: AgentGateway,
    capability_registry: CapabilityRegistry | None = None,
    workspace_root: Path | None = None,
    execution_context: ExecutionContext | None = None,
    extra: tuple[Plugin, ...] = (),
) -> Host:
    """``plan`` bundle: stores + tools + approval + workspace + workflow + llm."""
    from molab.workspace.plugin import WorkspacePlugin

    host = Host()
    root = (
        Path(workspace_root)
        if workspace_root is not None
        else execution_context.get_dir("work")
        if execution_context is not None
        else Path(run_dir)
    )
    host.mount(
        RunStoresPlugin(
            run_id=run_id,
            run_dir=Path(run_dir),
            workspace_root=root,
            execution_context=execution_context,
        )
    )
    if capability_registry is not None:
        host.mount(CapabilitiesPlugin(capability_registry))
    host.mount(ToolsPlugin())
    host.mount(ApprovalPlugin())
    host.mount(WorkspacePlugin(root))
    host.mount(WorkflowPlugin())
    host.mount(AgentCallPlugin(gateway))
    _mount_extra(host, extra)
    return host


def compose_curate(
    *,
    run_id: str,
    run_dir: Path,
    workspace_root: Path,
    gateway: AgentGateway | None = None,
    capability_registry: CapabilityRegistry | None = None,
    extra: tuple[Plugin, ...] = (),
    execution_context: ExecutionContext | None = None,
) -> Host:
    """``curate`` bundle: run-local stores; Stage root is the real workspace."""
    host = Host()
    host.mount(
        RunStoresPlugin(
            run_id=run_id,
            run_dir=Path(run_dir),
            workspace_root=Path(workspace_root),
            execution_context=execution_context,
        )
    )
    if capability_registry is not None:
        host.mount(CapabilitiesPlugin(capability_registry))
    if gateway is not None:
        host.mount(ToolsPlugin())
        host.mount(ApprovalPlugin())
        host.mount(AgentCallPlugin(gateway))
    _mount_extra(host, extra)
    return host


def compose_run(
    *,
    run_id: str,
    run_dir: Path,
    workspace_root: Path | None = None,
    executor: Executor | None = None,
    extra: tuple[Plugin, ...] = (),
    execution_context: ExecutionContext | None = None,
) -> Host:
    """``run`` bundle: stores + executor + workspace + workflow. Science extras last."""
    from molab.workspace.plugin import WorkspacePlugin

    host = Host()
    root = Path(workspace_root) if workspace_root is not None else Path(run_dir)
    host.mount(
        RunStoresPlugin(
            run_id=run_id,
            run_dir=Path(run_dir),
            workspace_root=workspace_root,
            execution_context=execution_context,
        )
    )
    host.mount(ExecutorPlugin(executor))
    host.mount(WorkspacePlugin(root))
    host.mount(WorkflowPlugin())
    _mount_extra(host, extra)
    return host
