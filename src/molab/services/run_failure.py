"""``analyze_run_failure`` — ordinary Run → sourced Report.

Shared by CLI, server, and (optionally) lifecycle tools so Python ≡ UI.
Deterministic narrative path needs **no** LLM: Execution error / execution
inventory. Optional ``narrative=`` overrides the template.

The write goes through :meth:`molab.knowledge.Report.harvest`: the knowledge
package owns execution→knowledge, so this module owns only the failure gate and
the deterministic narrative, never the storage shape.

Default domain is ``failed`` only; ``cancelled`` requires ``force=True``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.knowledge import Report

if TYPE_CHECKING:
    from molab.knowledge import Knowledge
    from molab.workspace.run import Run

__all__ = ["analyze_run_failure", "build_failure_narrative"]

_DEFAULT_NAME_PREFIX = "failure-analysis"


def build_failure_narrative(run: Run) -> str:
    """Build a non-empty deterministic Report narrative for *run*.

    Prefers the latest Execution's error, then a status-only summary.
    Never returns empty string.
    """
    status = run.status_label
    lines = [
        f"Run `{run.id}` finished with status `{status}`.",
        "",
        "## Evidence",
        "",
    ]
    error_text = _read_error_text(run)
    if error_text:
        lines.append("### Execution error")
        lines.append("")
        lines.append("```")
        lines.append(error_text)
        lines.append("```")
        lines.append("")
    else:
        lines.append("(no Execution error recorded)")
        lines.append("")

    history = list(run.executions)
    if history:
        lines.append("### Executions")
        lines.append("")
        for rec in history:
            exec_id = getattr(rec, "id", None) or "?"
            status = getattr(rec, "status", "?")
            lines.append(f"- `{exec_id}`: {status}")
        lines.append("")

    lines.append("## Resume")
    lines.append("")
    lines.append(
        "Use `resume` to open a new Execution based on the latest attempt "
        "and recompute unfinished nodes, "
        "or `rerun` for a fresh attempt. Re-run analyze-failure after the next "
        "terminal failure to update this note."
    )
    return "\n".join(lines).rstrip() + "\n"


def analyze_run_failure(
    run: Run,
    *,
    created_by: str,
    narrative: str | None = None,
    force: bool = False,
    name: str | None = None,
) -> Knowledge:
    """Write/update a Report for a failed *run*.

    Args:
        run: Workspace Run to interpret.
        created_by: Author string (``cli``, ``ui``, ``agent:…``).
        narrative: Optional override; when omitted a deterministic template is used.
        force: When True, also accept ``cancelled``; default is failed-only.
        name: Explicit document name; default ``failure-analysis-{run.id}``.

    Returns:
        The written :class:`~molab.knowledge.Knowledge`.

    Raises:
        ValueError: Status domain refusal or empty effective narrative.
    """
    status = run.status_label
    if status == "failed" or (force and status == "cancelled"):
        pass
    else:
        raise ValueError(
            f"run {run.id} is {status!r} — analyze_run_failure requires status "
            f"'failed' (or 'cancelled' with force=True)"
        )

    text = (narrative or "").strip() or build_failure_narrative(run)
    item_name = name or f"{_DEFAULT_NAME_PREFIX}-{run.id}"
    return Report.harvest(run, narrative=text, created_by=created_by, name=item_name)


def _read_error_text(run: Run) -> str:
    """Best-effort error body from the latest Execution record."""
    history = list(run.executions)
    if not history:
        return ""
    last = history[-1]
    err = last.error
    evidence = f"Execution evidence under {run.execution_dir(last.id)}"
    if not err:
        return evidence
    return f"{err.get('type', '?')}: {err.get('message', '?')}\n{evidence}"
