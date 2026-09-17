"""Production gateway builder for the server/CLI curation flow.

Mirrors ``server/plan_runtime/gateway.py``: builds the production
``RouterBackedAgentGateway`` for the one curation agent (``curation_planner``,
whose structured output is a :class:`~molab.harness.services.curate_runtime.flow.CurationInvocation`),
with a module-level factory seam so tests inject a ``StubAgentGateway`` instead
of constructing a real ``PydanticAIRouter``. The curate gateway config lives
here (server-tier) rather than in ``harness/gateways`` because curation is a
server-tier flow, not a harness Mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

    from molab.harness.gateways.gateway import AgentGateway
    from molab.workspace.run import Run

    CurateGatewayFactory = Callable[[Run, str], AgentGateway]

__all__ = [
    "build_curate_gateway",
    "curate_agent_responses",
    "curate_output_kinds",
    "curate_system_prompts",
    "reset_curate_gateway_factory",
    "set_curate_gateway_factory",
]

_CURATION_PLANNER_PROMPT = (
    "You plan a single workspace-curation action. Given the natural-language "
    "request and the capability catalog, choose exactly one capability by id and "
    "return a CurationInvocation: its `capability_id`, a `references` map of "
    "JSON-able handles for the capability's parameters (run/experiment ids, "
    "scalars — never live objects), and a one-line `reason`. Encoding rules: "
    "rehome_asset scope refs are colon-encoded strings — source: "
    "'experiment:exp-a', target: 'project:demo'; list-valued parameters "
    "(execution_ids, statuses) are comma-joined strings; booleans (fresh, "
    "recursive) are 'true'/'false'."
)


def curate_agent_responses() -> dict[str, type[BaseModel]]:
    """Map each curate agent name to its structured-output model class."""
    from molab.harness.services.curate_runtime.flow import CurationInvocation

    return {"curation_planner": CurationInvocation}


def curate_output_kinds() -> dict[str, str]:
    """Map each curate agent name to the artifact kind of its output."""
    return {"curation_planner": "curation_invocation"}


def curate_system_prompts() -> dict[str, str]:
    """Map each curate agent name to its system prompt."""
    return {"curation_planner": _CURATION_PLANNER_PROMPT}


# Test seam (mirrors plan_runtime.gateway): a factory(run, model).
_gateway_factory: CurateGatewayFactory | None = None


def set_curate_gateway_factory(factory: CurateGatewayFactory) -> None:
    """Install a test gateway factory called as ``factory(run, model)``."""
    global _gateway_factory
    _gateway_factory = factory


def reset_curate_gateway_factory() -> None:
    """Drop any installed test gateway factory."""
    global _gateway_factory
    _gateway_factory = None


def build_curate_gateway(*, model: str, run: Run) -> AgentGateway:
    """Build the production ``RouterBackedAgentGateway`` (or the test stub).

    The gateway's artifact store shares the run's ``artifacts`` directory with
    the flow-built context, so the planner output lands in one place.
    """
    if _gateway_factory is not None:
        return _gateway_factory(run, model)

    from molab.harness import RouterBackedAgentGateway
    from molab.harness.agent import PydanticAIRouter
    from molab.harness.agent.router import ModelTier
    from molab.harness.store.file_artifact_store import FileArtifactStore
    from molab.harness.store.paths import harness_artifact_root

    store = FileArtifactStore(root=harness_artifact_root(run.run_dir))
    router = PydanticAIRouter(models=dict.fromkeys(ModelTier, model))
    return RouterBackedAgentGateway(
        router=router,
        artifact_store=store,
        agent_responses=curate_agent_responses(),
        output_kind_by_agent=curate_output_kinds(),
        system_prompt_by_agent=curate_system_prompts(),
        model=model,
    )
