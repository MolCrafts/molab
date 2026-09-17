"""``molab plan`` — run the harness emergent-planning pipeline on a workspace.

The production call path into :mod:`molab.harness`: a natural-language
experiment draft is handed to :class:`~molab.harness.Plan`
on a ``workspace.Run``, driven by a
:class:`~molab.harness.gateways.router_backed.RouterBackedAgentGateway`
built from the configured LLM. The orchestrator runs two phases —
**phase 1** emergent planning (draft → task board → hard review gate → frozen
experiment plan) and **phase 2** deterministic realization (a separate phase,
not driven by this command yet). With no approver the review gate suspends
store-first (exit 2); a re-run with a stored grant replays through the gate.

Model resolution mirrors ``molab agent``: ``--model`` wins, else the
``agent.model`` key from ``molab config``; with neither, the command fails
with an actionable message.

Zero-residue ordering: draft + model resolution and the agent-stack
preflight (:meth:`PlanRuntime.preflight` → shared
``services.plan_runtime.preflight_plan_router``) all run BEFORE the first
workspace write, so a missing ``molab[agent]`` extra, an unconfigured
model, or a missing API key exits with a one-line message and leaves the
target directory untouched.

Heavy imports (``molab.harness``, ``molab.workspace``, the agent router)
are deferred into the command body so plain ``molab --help`` stays fast.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from molab.harness.agent.router import Router
    from molab.harness.gateways.gateway import AgentGateway
    from molab.harness.registry.capability_registry import CapabilityRegistry
    from molab.harness.schemas import ApprovalDecision, ApprovalRequest
    from molab.harness.services.plan_runtime import PlanRecordOutcome
    from molab.workspace.execution_context import ExecutionContext
    from molab.workspace.run import Run

__all__ = ["plan"]

_DRAFT_PREVIEW_CHARS = 80


class InteractiveApprover:
    """``Approver`` for ``molab plan``'s emergent review gate.

    A callable approver (satisfies the harness ``Approver`` type —
    ``async (ApprovalRequest) -> ApprovalDecision`` — via :meth:`__call__`). It
    auto-grants **only under an explicit ``--yes``**; the command constructs it
    solely on a TTY or with ``--yes``, and passes ``approve=None`` otherwise —
    the gate then suspends pending instead of granting. On an interactive
    terminal it renders the review pack for the request and prompts
    ``[a]pprove / [r]eject / [v]revise``.

    :class:`~molab.harness.Plan` receives it as its
    ``approve`` seam and asks it at the plan-tool side-effect gate and the hard
    ``approve_experiment_plan`` review gate before the plan is frozen.
    """

    def __init__(self, *, run: Run, assume_yes: bool = False) -> None:
        self._run = run
        self._assume_yes = assume_yes
        self._execution_context: ExecutionContext | None = None

    def bind_execution(self, context: ExecutionContext) -> None:
        """Bind the exact active Execution before the first review gate."""
        self._execution_context = context

    def _interactive(self) -> bool:
        import sys

        return not self._assume_yes and sys.stdin.isatty()

    async def __call__(self, request: ApprovalRequest) -> ApprovalDecision:
        from datetime import UTC, datetime

        from molab.harness.schemas import ApprovalDecision, ReviewDecision
        from molab.harness.services.plan_runtime.preview import (
            build_review_pack,
            render_review_pack,
        )
        from molab.harness.store.file_artifact_store import FileArtifactStore

        if not self._interactive():
            # Only reachable via --yes: the command constructs this approver
            # solely on a TTY or with --yes, so a non-interactive call IS the
            # operator's explicit blanket consent — named in the audit trail.
            return ApprovalDecision(
                request_id=request.id,
                granted=True,
                decided_by="cli---yes",
                decided_at=datetime.now(tz=UTC),
                reason="auto-granted (--yes)",
            )

        if self._execution_context is None:
            raise RuntimeError("interactive approver has no bound Execution")
        execution_id = str(self._execution_context.id)
        pack = build_review_pack(self._run, execution_id, request.intent)
        from molab.cli._common import rprint

        rprint("\n[bold]Review pack:[/bold]")
        for line in render_review_pack(pack).splitlines():
            rprint(f"  {line}")
        prompt = (
            "Approve this spec and compile the workflow?"
            if request.intent == "experiment_spec"
            else "Approve this plan as final?"
        )
        answer = (
            input(f"{prompt} [{request.intent}] [a]pprove / [r]eject / [v]revise: ").strip().lower()
        )
        if answer in ("a", "approve", "y", "yes"):
            action = "approve"
            granted = True
        elif answer in ("v", "revise"):
            action = "revise"
            granted = False
        else:
            # fail-closed: unknown / empty / r / reject → reject
            action = "reject"
            granted = False

        decision = ReviewDecision(
            pack_id=pack.pack_id,
            action=action,  # type: ignore[arg-type]
            decided_by="cli-interactive",
            decided_at=datetime.now(tz=UTC),
            reason=f"operator answered {answer!r}",
        )
        FileArtifactStore.for_execution(self._execution_context).put_json(
            kind="review_decision",
            obj=decision.model_dump(mode="json"),
            created_by="cli.InteractiveApprover",
            parent_ids=[],
        )
        return ApprovalDecision(
            request_id=request.id,
            granted=granted,
            decided_by="cli-interactive",
            decided_at=decision.decided_at,
            reason=decision.reason,
        )


def _print_record_errors(outcome: PlanRecordOutcome) -> None:
    """Surface record-materialization failures loudly (never exit-code-changing).

    The science and its artifacts are already safely on disk; the record layer
    is a projection — so a broken record prints a red block naming each failed
    record instead of silently vanishing into a log (no-silent-fallback law).
    """
    if not outcome.errors:
        return
    from molab.cli._common import rprint

    rprint("[red]record materialization failed for:[/red]")
    for error in outcome.errors:
        rprint(f"  - {error.record}: {error.error}")


def _configured_model() -> str | None:
    """Return the ``agent.model`` value from ``molab config``, if any.

    Delegates to the ``molab agent`` command's resolver so both commands
    read the same configuration key. A seam: tests monkeypatch this.
    """
    from molab.harness.cli.agent_cmd import _configured_model as agent_configured_model

    return agent_configured_model()


def _resolve_grounding(
    workspace_root: Path,
    *,
    ground: bool,
    task: str | None = None,
    sources: list[str] | None = None,
) -> CapabilityRegistry | None:
    """Build a molmcp-backed ``CapabilityRegistry`` when ``--ground`` is set.

    Returns ``None`` when grounding is off or molmcp is unavailable (the helper
    prints a visible notice in the latter case — never a silent downgrade).
    ``task`` is the experiment draft so discovery follows the user request
    (auto-discovery — no fixed polymer query table).

    ``sources`` pins knowledge packages (e.g. molpy, molvis, molplot) so the
    binder never sees out-of-scope catalogs like atomiverse.
    """
    if not ground:
        return None
    from molab.cli._common import rprint
    from molab.harness.mcp_capabilities import resolve_capability_registry

    return resolve_capability_registry(
        workspace_root,
        task=task,
        sources=sources,
        notify=lambda message: rprint(f"[dim]{message}[/dim]"),
    )


class PlanRuntime:
    @staticmethod
    def preflight(*, model: str) -> Router | None:
        """Validate the agent stack + credentials BEFORE any disk write.

        Delegates to :func:`molab.harness.services.plan_runtime.preflight_plan_router`
        (shared with the server path): imports the agent stack, constructs the
        router, and forces credential resolution — no network, no disk. Raises
        :class:`~molab.harness.services.plan_runtime.PlanPreflightError` with a
        one-line human-readable reason. A seam: tests monkeypatch this to a
        no-op returning ``None`` alongside a stubbed :meth:`build_gateway`.
        """
        from molab.harness.services.plan_runtime.gateway import preflight_plan_router

        return preflight_plan_router(model=model)

    @staticmethod
    def build_gateway(
        *,
        model: str,
        run: Run,
        router: Router | None = None,
        workspace_root: str | Path | None = None,
        task_id: str | None = None,
        draft: str | None = None,
        turn_id: str | None = None,
        knowledge_sources: list[str] | None = None,
    ) -> AgentGateway:
        """Build the production gateway for ``run`` from the resolved ``model``.

        Delegates to the shared service builder
        (:func:`molab.harness.services.plan_runtime.build_plan_gateway`) so the CLI
        and the server construct the exact same gateway; ``router`` reuses the
        instance :meth:`preflight` already validated. A seam: tests
        monkeypatch this to inject a ``StubAgentGateway`` instead.

        Pass ``workspace_root`` + ``task_id`` (+ optional ``draft``) so each
        LLM call is projected into the Agents-tab session cache.
        ``knowledge_sources`` pins molmcp package scope for this plan.
        """
        from molab.harness.services.plan_runtime.gateway import build_plan_gateway

        return build_plan_gateway(
            model=model,
            run=run,
            router=router,
            workspace_root=workspace_root,
            task_id=task_id,
            draft=draft,
            turn_id=turn_id,
            knowledge_sources=knowledge_sources,
        )


def _resolve_draft(draft: str | None, file: Path | None) -> str:
    """Return the draft text from exactly one of ``draft`` / ``file``."""
    from molab.cli._common import rprint

    if (draft is None) == (file is None):
        rprint(
            "[red]Provide the draft exactly one way:[/red] either as the "
            "[bold]DRAFT[/bold] argument or via [bold]--file <path>[/bold]."
        )
        raise typer.Exit(1)
    if file is not None:
        try:
            text = file.read_text(encoding="utf-8")
        except OSError as exc:
            rprint(f"[red]Could not read draft file:[/red] {exc}")
            raise typer.Exit(1) from exc
    else:
        assert draft is not None  # narrowed by the exactly-one check above
        text = draft
    if not text.strip():
        rprint("[red]The experiment draft is empty.[/red]")
        raise typer.Exit(1)
    return text


def plan(
    draft: Annotated[
        str | None,
        typer.Argument(help="Natural-language experiment draft (or use --file)."),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Read the experiment draft from a file."),
    ] = None,
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", help="Workspace root; defaults to the current directory."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model id; defaults to `molab config` agent.model."),
    ] = None,
    project: Annotated[
        str,
        typer.Option("--project", help="Project the plan run is filed under."),
    ] = "plans",
    experiment: Annotated[
        str,
        typer.Option("--experiment", help="Experiment the plan run is filed under."),
    ] = "plan",
    execute: Annotated[
        bool,
        typer.Option(
            "--execute",
            help="Request the phase-2 deterministic realization tail after the "
            "plan is approved. Realization is a separate phase not yet driven by "
            "this command — `molab plan` stops at the frozen plan + report; "
            "passing --execute prints a notice.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes/--non-interactive",
            "-y",
            help="Auto-approve the experiment-report review checkpoint. The "
            "default already auto-approves when stdin is not a TTY (CI/pipes).",
        ),
    ] = False,
    ground: Annotated[
        bool,
        typer.Option(
            "--ground/--no-ground",
            help="Ground task binding against the molcrafts toolchain via the "
            "configured `molmcp` MCP server: the binder picks capabilities from "
            "the live catalog and ValidateBoundWorkflow checks each bound "
            "capability exists, its call shape, and its backend. On by default; "
            "skips with a notice when molmcp is not available. Use --no-ground "
            "to disable.",
        ),
    ] = True,
    sources: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            "-S",
            help="Pin molmcp knowledge packages for this plan (repeatable). "
            "Example: -S molpy -S molvis -S molplot. When set, molmcp only "
            "exposes those packages (atomiverse etc. are hidden) and the "
            "capability catalog is filtered the same way.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show the produced artifacts of the two-phase plan flow "
            "(emergent planning → deterministic realization) on completion.",
        ),
    ] = False,
) -> None:
    """Turn an experiment draft into a frozen experiment plan (emergent planning)."""
    from molab.cli._common import rprint
    from molab.harness import ApprovalPendingError, Plan, StageExecutionError
    from molab.harness.services.plan_runtime import PlanPreflightError
    from molab.workspace import Workspace

    draft_text = _resolve_draft(draft, file)

    resolved_model = model or _configured_model()
    if not resolved_model:
        rprint(
            "[red]No model configured.[/red] Pass [bold]--model <id>[/bold] or run "
            "[bold]molab config set agent.model <id>[/bold]."
        )
        raise typer.Exit(1)

    # Preflight — BEFORE any disk write. A missing agent extra, an unknown
    # model, or a missing API key exits here with a one-line reason and
    # leaves the workspace directory untouched (zero residue).
    try:
        router = PlanRuntime.preflight(model=resolved_model)
    except PlanPreflightError as exc:
        from rich.markup import escape

        # escape(): the message may contain rich-markup-lookalikes ("[agent]").
        rprint(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(1) from exc

    workspace_root = (workspace or Path.cwd()).resolve()
    ws = Workspace(workspace_root)
    ws.materialize()
    # Content-addressed run: same bootstrap as POST /plan-tasks.
    exp = ws.add_project(project).add_experiment(experiment)
    plan = Plan.open(exp, draft_text, realize=True)
    run = plan.bound_run

    # Explicit or suspended, never implicit: an interactive approver exists
    # only on a TTY or with --yes; otherwise approve=None means the review gate
    # resolves store-first and SUSPENDS pending (exit 2) instead of granting.
    import sys

    plan.approve = (
        InteractiveApprover(run=run, assume_yes=yes) if (yes or sys.stdin.isatty()) else None
    )
    preview = draft_text.strip().splitlines()[0][:_DRAFT_PREVIEW_CHARS]
    rprint(f"[bold]molab plan[/bold] — plan pipeline on run [bold]{run.id}[/bold]")
    rprint(f"  model     : {resolved_model}")
    rprint(f"  draft     : {preview}")
    rprint(f"  workspace : {workspace_root}")
    rprint("  phase 1   : planning (draft → task board → review gate → frozen plan)")
    rprint("  phase 2   : realization (bound board → codegen → compile)")

    plan_task_id = f"plan-{run.id}"
    source_list = [s.strip() for s in (sources or []) if s and str(s).strip()] or None
    if source_list:
        rprint(f"  sources   : {', '.join(source_list)}")
    gateway = PlanRuntime.build_gateway(
        model=resolved_model,
        run=run,
        router=router,
        workspace_root=str(workspace_root),
        task_id=plan_task_id,
        draft=draft_text,
        knowledge_sources=source_list,
    )
    capability_registry = _resolve_grounding(
        workspace_root,
        ground=ground,
        task=draft_text,
        sources=source_list,
    )
    try:
        result = asyncio.run(
            plan.execute(
                gateway=gateway,
                capability_registry=capability_registry,
            )
        )
    except ApprovalPendingError as exc:
        # Suspended, not failed: the pending request is persisted in the run's
        # approval store; a decision lets a re-run resume past the gate.
        rprint(f"[yellow]Plan suspended — approval pending:[/yellow] {exc}")
        for request in exc.requests:
            rprint(f"  - [{request.intent}] {request.reason}")
        rprint(
            "[dim]To proceed: decide in the UI approvals inbox, re-run this "
            "command on a TTY to answer interactively, or re-run with --yes. "
            "A granted plan review replays store-first through the gate on the "
            "same run.[/dim]"
        )
        raise typer.Exit(2) from exc
    except StageExecutionError as exc:
        rprint(f"[red]Plan pipeline failed:[/red] {exc}")
        rprint(
            "[dim]The plan board was rejected before the review gate opened — "
            "re-running the same draft regenerates it.[/dim]"
        )
        # A terminally-failed plan still materializes (Agents-tab entry with
        # status failed + a FailureAnalysis knowledge record). The suspension
        # path above never reaches here — ApprovalPendingError is not a failure.
        from molab.harness.services.plan_runtime import PlanFailure
        from molab.harness.services.plan_runtime.materialize import materialize_plan_records

        failed_execution_id = plan.last_execution_id
        if failed_execution_id is None:
            raise typer.Exit(1) from exc
        outcome = materialize_plan_records(
            run=run,
            experiment=exp,
            workspace_root=str(workspace_root),
            task_id=plan_task_id,
            draft=draft_text,
            model=resolved_model,
            execution_id=failed_execution_id,
            failure=PlanFailure(stage=None, error=str(exc)),
        )
        _print_record_errors(outcome)
        raise typer.Exit(1) from exc

    rprint("\n[green]OK[/green] emergent plan completed")
    rprint(f"  artifacts : {len(result.stage_artifacts)} produced")
    if verbose:
        for ref in result.stage_artifacts:
            rprint(f"    {ref.kind:<24} {ref.id}")
    if result.final_artifact is not None:
        rprint(f"  final     : {result.final_artifact.kind}  {result.final_artifact.id}")

    # Materialize the SAME UI-facing records the server's `POST /plan-tasks`
    # writes — persist the workflow IR onto the experiment + record the Agents
    # session (with the deliverables locator) and Knowledge note — so a plan
    # produced here is identical, in the UI, to one generated from the web app.
    from molab.harness.services.plan_runtime.materialize import materialize_plan_records

    outcome = materialize_plan_records(
        run=run,
        experiment=exp,
        workspace_root=str(workspace_root),
        task_id=plan_task_id,
        draft=draft_text,
        model=resolved_model,
        execution_id=result.execution_id,
    )
    _print_record_errors(outcome)
    rprint(f"  ui session: [bold]{plan_task_id}[/bold] (open the Agents tab to see this plan)")

    if execute:
        # Honest notice: the emergent orchestrator is planning-only. Real
        # execution / realization (phase 2) is a separate phase this command
        # does not drive yet — never a silent success claim.
        rprint(
            "[yellow]--execute[/yellow]: deterministic realization (phase 2) is a "
            "separate phase not driven by this command yet — the plan stops at the "
            "frozen plan + report."
        )

    rprint(f"\n  artifacts : {run.run_dir / 'harness' / 'artifacts'}")
    rprint(f"  events    : {run.run_dir / 'events.jsonl'}")
    rprint(f"  approvals : {run.run_dir / 'approvals.json'}")
    rprint(
        "[dim]Re-running the same draft replays store-first through the review "
        "gate on the same content-addressed run.[/dim]"
    )
