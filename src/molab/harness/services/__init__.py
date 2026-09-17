"""Application services owned by the harness — one backend path per operation.

The CLI commands (``molab plan`` / ``molab curate`` / ``molab agent``) and
the harness server routes both delegate here instead of duplicating logic or
importing each other ("Python operation ≡ UI operation").

Contents:

- :mod:`~molab.harness.services.plan_runtime` — plan gateway builder +
  preflight, background-task registry, and the post-run
  record/persist/materialize steps.
- :mod:`~molab.harness.services.curate_runtime` — the shared curation flow
  (discover → plan → gate → invoke) + proposal backend.
- :mod:`~molab.harness.services.agent_task_store` — on-disk metadata/events
  for user-facing agent tasks.
- :mod:`~molab.harness.services.agent_task_llm_cache` — LLM call traces
  attached to those tasks.
- :mod:`~molab.harness.services.agent_context` — the one mount-context
  builder for ``molab agent`` and server session create.
- :mod:`~molab.harness.services.approval_notify` — in-process
  approval-change pub/sub (payload-free SSE pings).

Layer rules: this package may import the rest of ``molab.harness`` and any
molab layer below it. It MUST NOT import ``molab.server`` or
``molab.cli`` — those shells sit above it and import it, never the reverse.

No eager re-exports: importing this package stays light.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from molab.harness.services.agent_context import (
        build_mount_context,
        mount_session_scope,
        resolve_scope_dir,
    )

__all__ = ["build_mount_context", "mount_session_scope", "resolve_scope_dir"]


def __getattr__(name: str) -> object:
    if name in __all__:
        from molab.harness.services import agent_context

        return getattr(agent_context, name)
    raise AttributeError(f"module 'molab.harness.services' has no attribute {name!r}")
