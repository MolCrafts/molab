"""``drive_plan_mode`` — the ONE way CLI and server run a PlanOrchestrator pipeline.

Wraps ``mode.run(...)`` in the run's own lifecycle (``run.start()``), so a
plan Run's workspace status is honest: ``running`` while the pipeline
executes (with the ownership stamp + heartbeat every workflow run gets),
``succeeded`` when all stages complete, ``failed`` when a stage raises.
Without this, a plan run stayed ``pending`` forever and every status
surface in the UI contradicted the 13 green pipeline steps.

Plan re-entry stays governed by the stage ledger, NOT the run verbs: a
re-run against a ``succeeded`` plan run enters the lifecycle again (ledger
hits make it cheap), unlike ``molexp run`` which refuses succeeded runs.
A concurrently *running* plan on the same Run is still refused by the
lifecycle's ownership claim — one Run, one live execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from molexp.harness import CapabilityRegistry, ModeResult
    from molexp.harness.gateways.gateway import AgentGateway
    from molexp.workspace.run import Run

__all__ = ["drive_plan_mode", "resolve_plan_run"]


def resolve_plan_run(experiment: Any, draft: str, *, supersedes: str | None = None) -> Run:  # noqa: ANN401
    """Content-addressed plan Run bootstrap — same draft ⇒ same Run.

    The ONE bootstrap shared by ``molexp plan`` and ``POST /plan-tasks``
    ("Python 操作 = UI 操作"): the run id is derived from the canonical
    params (``mode``/``draft`` and, when a plan supersedes an earlier one,
    ``supersedes`` — a superseding plan is a *different* logical run), and
    ``add_run`` is idempotent on that id, so re-driving the same draft
    replays store-first on the same Run instead of minting a new one.
    """
    from molexp._typing import JSONValue
    from molexp.workspace.utils import derive_run_id

    params: dict[str, JSONValue] = {"mode": "plan", "draft": draft}
    if supersedes:
        params["supersedes"] = supersedes
    return experiment.add_run(params, id=derive_run_id(params))


class _ModeLike(Protocol):
    async def run(
        self,
        *,
        run: Any,  # noqa: ANN401 — workspace Run, duck-typed for tests
        user_input: str,
        gateway: Any,  # noqa: ANN401
        capability_registry: Any = None,  # noqa: ANN401
    ) -> Any: ...  # noqa: ANN401


async def drive_plan_mode(
    mode: _ModeLike,
    *,
    run: Run,
    user_input: str,
    gateway: AgentGateway,
    capability_registry: CapabilityRegistry | None = None,
) -> ModeResult:
    """Run *mode* against *run* inside the run lifecycle; return its result.

    Success marks the run ``succeeded`` explicitly (the lifecycle never
    defaults to success); a raising stage propagates after the lifecycle
    records ``failed``.
    """
    with run.start() as run_ctx:
        result = await mode.run(
            run=run,
            user_input=user_input,
            gateway=gateway,
            capability_registry=capability_registry,
        )
        run_ctx.mark_succeeded()
    return result
