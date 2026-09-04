"""``harvest_run`` — turn a finished Run's outcome into typed knowledge.

The explicit execution→knowledge verb for plain runs (vision-loop-06): a
researcher (or, later, an agent capability) harvests a terminal run into a
source-attributed :class:`Knowledge` mounted under the run's experiment.

Harvesting is **interpretation, not archival**: the run's raw record already
lives in ``run.json``/artifacts, so a harvest without a narrative is refused —
knowledge is what the numbers *mean*. Preconditions error, never fall back:

* the run must be terminal (``succeeded`` / ``failed`` / ``cancelled``) — a
  live run has no outcome to interpret yet;
* ``narrative`` must be non-empty.

Placement rationale: workspace-only imports (Run / Knowledge / Folder), so
the P1 lifecycle-capability slice can expose this as a harness
``ToolCapability`` (harness→workspace is legal; harness→services is not).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molexp.ids import slugify

from .domain import ExecutionStatus
from .knowledge import Knowledge, SourceRef
from .knowledge_write import write_knowledge
from .run import TERMINAL_STATUSES as _TERMINAL_STATUSES

if TYPE_CHECKING:
    from molexp._typing import JSONValue

    from .run import Run

__all__ = ["harvest_run"]

_MAX_VALUE_CHARS = 400
"""Per-value cap in the rendered results table (repr-truncated)."""


def _scalar_status(run: Run) -> str:
    """Derive the single run-status label from the Execution aggregate."""
    summary = run.status_summary
    if summary.not_started:
        return "pending"
    if summary.active > 0:
        return "running"
    for status in ("failed", "cancelled", "interrupted", "succeeded"):
        if summary.by_status.get(status):
            return status
    return "succeeded" if summary.total else "pending"


def _last_error(run: Run) -> str | None:
    """Return the message of the most recent failed Execution, if any."""
    for state in run.executions:
        if state.status is ExecutionStatus.FAILED and state.error:
            return str(state.error.get("message") or state.error.get("type") or state.error)
    return None


def harvest_run(
    run: Run,
    *,
    cls: type[Knowledge],
    narrative: str,
    created_by: str,
    results: dict[str, JSONValue] | None = None,
    name: str | None = None,
) -> Knowledge:
    """Harvest a terminal *run* into sourced Knowledge under its experiment."""
    status = _scalar_status(run)
    if status not in _TERMINAL_STATUSES:
        raise ValueError(
            f"run {run.id} is {status!r} — only a terminal run "
            f"({sorted(_TERMINAL_STATUSES)}) has an outcome to harvest"
        )
    if not narrative.strip():
        raise ValueError(
            "harvest requires a non-empty narrative — knowledge is interpretation; "
            "the raw record already lives in run.json and the run's artifacts"
        )

    experiment = run.experiment
    item_name = name or f"{slugify(cls.__name__)}-{run.id}"
    return write_knowledge(
        experiment,
        name=item_name,
        cls=cls,
        sources=[
            SourceRef(kind="run", ref=run.id),
            SourceRef(kind="experiment", ref=experiment.id),
        ],
        created_by=created_by,
        body=_render_body(run, cls=cls, narrative=narrative, results=results),
        cite=[(run, "derived_from")],
    )


def _render_body(
    run: Run,
    *,
    cls: type[Knowledge],
    narrative: str,
    results: dict[str, JSONValue] | None,
) -> str:
    status = _scalar_status(run)
    lines = [
        f"# [{cls.__name__}] run {run.id}",
        "",
        narrative.strip(),
        "",
        "## Run",
        "",
        f"- status: {status}",
    ]
    params = run.metadata.parameters
    if params:
        lines.append(f"- params: {_truncate(repr(params))}")
    error = _last_error(run)
    if status == "failed" and error:
        lines += ["", "## Error", "", _truncate(error)]
    if results:
        lines += ["", "## Results", ""]
        lines += [f"- **{key}**: {_truncate(repr(value))}" for key, value in results.items()]
    return "\n".join(lines).rstrip() + "\n"


def _truncate(text: str) -> str:
    if len(text) <= _MAX_VALUE_CHARS:
        return text
    return text[:_MAX_VALUE_CHARS] + f"… (+{len(text) - _MAX_VALUE_CHARS} chars)"
