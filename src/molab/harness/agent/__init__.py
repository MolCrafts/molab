"""Public agent surface — pydantic-ai facade.

The user-visible surface is four names — :class:`AgentRunner`,
:class:`AgentRunResult`, :class:`AgentRuntime`, :class:`AgentSession` —
plus one **lazy** re-export: ``PydanticAIRouter``.

There is no molab-owned conversation loop. Chat is one
``Router.complete_text``. Tool-using work is one ReAct
(``Router.stream_agentic``). Plan orchestration is a
:class:`~molab.workflow.WorkflowCompiler` graph in harness.

Layer position: **agent uses workspace only**. It **MUST NOT** import
:mod:`molab.workflow`, :mod:`molab.harness`, or any sibling
application layer. The harness imports agent via the sanctioned
``agent.router`` Protocol edge.

``import molab.harness.agent`` does not eagerly load ``pydantic_ai``.
"""

from typing import TYPE_CHECKING

from molab.harness.agent.loop import AgentRunResult
from molab.harness.agent.runner import AgentRunner
from molab.harness.agent.runtime import AgentRuntime
from molab.harness.agent.session import Session as AgentSession

if TYPE_CHECKING:
    from molab.harness.agent._pydanticai.router import PydanticAIRouter as PydanticAIRouter

__all__ = [
    "AgentRunResult",
    "AgentRunner",
    "AgentRuntime",
    "AgentSession",
]


def __getattr__(name: str) -> object:
    """Lazy re-export — keeps ``import molab.harness.agent`` pydantic-ai-free."""
    if name == "PydanticAIRouter":
        from molab.harness.agent._pydanticai.router import PydanticAIRouter

        return PydanticAIRouter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
