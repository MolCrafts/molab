# Agent Layer Architecture

The agent layer (`molab.harness.agent`) is a clean, user-facing wrapper around
[pydantic-ai](https://github.com/pydantic/pydantic-ai). The library is
an implementation detail hidden inside the private `_pydanticai/`
subpackage and **never appears in the public surface**.
(`pydantic_graph` is not a molab dependency at all and is never imported
under `agent/` — see the confinement rule below.)

## Public API

The agent layer exposes four user-visible names:

```python
from molab.harness.agent import (
    AgentRunner, AgentRunResult, AgentRuntime, AgentSession,
)
```

Chat is one `Router.complete_text` (`AgentRunner(mode="text")`).
Tool-using work is one ReAct (`mode="agentic"` → `Router.stream_agentic`).
Plan orchestration is a harness workflow, not an agent loop.

Construction is plain Python — no factory functions
(`create_agent(...)` / `build_agent(...)` / `Agent(provider=...)`).
`AgentRunner(*, model=…, router=…)` lazily builds the underlying
pydantic-ai router on first `.run()`, so `import molab.harness.agent` is cheap.
A loop receives an `AgentRuntime` (`session` + `router` +
`execution_env`) and emits everything it sees through the injected
`AsyncIteratorEventSink`.

## Layer Boundaries

```text
harness ──uses──▶ agent ──uses──▶ workspace
                  (agent and workflow are SIBLINGS — no edge between them)
```

`molab.harness.agent` may import from `molab.workspace.*` (the storage layer
below it). It must **not** import `molab.workflow` or `molab.harness`
— workflow is a sibling and harness sits above; harness reaches the
agent layer through `molab.harness.agent.router` (the SDK-free `Router`
Protocol module). It must also not import sibling application layers
(`molab.plugins`, `molab.server`, `molab.cli`).

### pydantic-ai firewall

The only files under `src/molab/harness/agent/` allowed to `import pydantic_ai`
live inside `agent/_pydanticai/`:

| File | Purpose |
|---|---|
| `_pydanticai/router.py` | `PydanticAIRouter` — concrete `Router` implementation; one `Agent` instance per `(tier, schema \| None)` |
| `_pydanticai/mcp.py` | `build_mcp_server` helper used to attach MCP toolsets to a loop |
| `_pydanticai/messages_codec.py` | message-history (de)serialization between molab sessions and pydantic-ai |
| `_pydanticai/errors.py` | `ProviderError` — the single SDK-failure boundary |

The firewall is owed by the rewritten harness test suite — see
`.claude/notes/harness-invariants-to-restore.md`. The layer boundary that
*is* enforced today is the other direction: `tests/test_import_direction.py`
fails the build if molab imports the harness at all.
`import molab.harness.agent` does not eagerly load `pydantic_ai` — every
construction site is hidden behind a lazy import that fires only on the
first `AgentRunner.run()` call.

### pydantic-graph removal

molab has no `pydantic_graph` dependency — the workflow engine
(`src/molab/workflow/_engine/`) is molab-owned, and **nothing under
`src/` may import `pydantic_graph`** (agent included). The agent never
schedules a workflow itself; the harness does, and even there the
engine runs in an executor subprocess rather than in-process.

## Don't Reinvent pydantic-ai

> Anything pydantic-ai provides natively in *model-side execution* (tool
> dispatch, MCP, retries, message history, structured output) MUST use
> pydantic-ai; do not build parallel implementations under
> `molab.harness.agent`.

Concrete consequences:

* Tools — pass `pydantic_ai.tools.Tool` instances or bare callables to
  `AgentRunner(tools=...)`; the router forwards them verbatim into
  `Agent(tools=...)`. No molab middle layer.
* MCP servers — `Agent(toolsets=[MCPServerStdio(...)])`. molab does not
  iterate over MCP needs by hand.
* Retries — `Agent(retries=N)`. The router's outer retry budget on top
  of pydantic-ai is a structured-path safety net, not a re-implementation.
* Message history — pydantic-ai's `RunResult.all_messages()` and
  `Agent(message_history=...)`.
* Structured output — `Agent(output_type=Schema)`.

molab retains ownership of the **session / event / on-disk** layer
(`Session` persistence, the `AgentEvent` stream, the `Agent` /
`AgentSession` folders) because pydantic-ai does not cover those. The
multi-stage experiment pipeline is owned by `molab.harness`, one layer
up.

## Pipeline orchestration lives in the harness

The agent layer used to host its own multi-step pipelines (PlanOrchestrator,
AuthorMode, RunMode, ReviewMode) built on `molab.workflow`. That
orchestration moved out: `molab.harness` now owns the `Mode` ledger
and the canonical `PlanOrchestrator` (two-phase planning + realization
tail; the former separate RunMode is retired/folded in). The harness
drives the LLM through the agent's
`Router` Protocol via `RouterBackedAgentGateway` — the single sanctioned
`harness → agent` edge. See [Plan Mode Architecture](plan-mode.md) for
the stage list and artifact layout.

## Sessions and events

A conversation is recorded by a `Session` (re-exported as
`AgentSession`): an append-only entry tree with a leaf pointer.
Persistence is pluggable behind the `SessionStorage` Protocol —
`JsonlSessionStorage` on disk, `InMemorySessionStorage` in tests.
On-disk, an `Agent` folder (`kind = "agent.agent"`) and `AgentSession`
folder (`kind = "agent.session"`) attach to any workspace `Folder`
through the generic `add_folder` CRUD, so the workspace layer never
learns their agent-specific shape.

Every observable step a loop takes is emitted as an `AgentEvent`
(a discriminated union) through an `AsyncIteratorEventSink`. The CLI's
`AgentEventRenderer` and the server's SSE stream consume the same event
contract, so terminal and web clients render identical conversations.
