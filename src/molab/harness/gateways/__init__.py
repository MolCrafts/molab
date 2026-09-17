"""Agent gateway contract + production implementations for ``molab.harness``.

Phase 2 shipped only the :class:`AgentGateway` Protocol. Spec
``harness-as-mode-substrate-03a`` adds the production
:class:`RouterBackedAgentGateway` impl, driven by
:class:`molab.harness.agent.router.Router`. The in-memory
:class:`StubAgentGateway` lives at ``molab.harness.gateways.stub`` and is
intentionally **not** re-exported — tests reach for it via its full
dotted path so a stray ``from molab.harness.gateways import StubAgentGateway``
will fail loudly.
"""

from __future__ import annotations

from molab.harness.gateways.call_runtime import AgentCallRuntime
from molab.harness.gateways.gateway import AgentGateway
from molab.harness.gateways.llm_trace import LlmCallObserver, LlmCallTrace
from molab.harness.gateways.plan_agents import (
    plan_agent_mcp_servers,
    plan_agent_responses,
    plan_agent_tiers,
    plan_output_kinds,
    plan_system_prompts,
)
from molab.harness.gateways.router_backed import RouterBackedAgentGateway

__all__ = [
    "AgentCallRuntime",
    "AgentGateway",
    "LlmCallObserver",
    "LlmCallTrace",
    "RouterBackedAgentGateway",
    "plan_agent_mcp_servers",
    "plan_agent_responses",
    "plan_agent_tiers",
    "plan_output_kinds",
    "plan_system_prompts",
]
