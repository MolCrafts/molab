"""``harvest_run`` — turn a finished Run's outcome into typed knowledge.

The explicit execution→knowledge verb for plain runs: a researcher harvests
a terminal run into a source-attributed Knowledge document mounted under the
run's experiment.

Harvesting is **interpretation, not archival**: the run's raw record already
lives in ``run.json``/artifacts, so a harvest without a narrative is refused —
knowledge is what the numbers *mean*. Preconditions error, never fall back:

* the run must be terminal (``succeeded`` / ``failed`` / ``cancelled``) — a
  live run has no outcome to interpret yet;
* ``narrative`` must be non-empty.

A ``Run`` is a legitimate argument here: ``molab.knowledge`` depends on
``molab.workspace``, and every such import is confined to a function body so
the package import stays acyclic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from molab.ids import slugify

from .concept import Knowledge
from .knowledge_item import SourceRef
from .write import write_knowledge

if TYPE_CHECKING:
    from molab._typing import JSONValue
    from molab.workspace.run import Run

__all__ = ["harvest_run"]

_MAX_VALUE_CHARS = 400
"""Per-value cap in the rendered results table (repr-truncated)."""


def _last_error(run: Run) -> str | None:
    """Return the message of the most recent failed Execution, if any."""
    from molab.workspace.domain import ExecutionStatus

    for state in run.executions:
        if state.status is ExecutionStatus.FAILED and state.error:
            return str(state.error.get("message") or state.error.get("type") or state.error)
    return None


def harvest_run(
    run: Run,
    of: type[Knowledge],
    *,
    narrative: str,
    created_by: str,
    results: dict[str, JSONValue] | None = None,
    name: str | None = None,
) -> Knowledge:
    """Harvest a terminal *run* into sourced Knowledge under its experiment.

    Args:
        run: The terminal run whose outcome is being interpreted.
        of: Knowledge subclass — this **is** the category.
        narrative: The interpretation; blank is refused.
        created_by: Author (person or ``agent:…``).
        results: Optional result table rendered into the body (values truncated).
        name: Explicit document name; defaults to ``<kind>-<run id>``, which
            makes a re-harvest of the same run and kind update in place.

    Returns:
        The harvested Knowledge document.

    Raises:
        ValueError: If *run* is not terminal, or *narrative* is blank.
    """
    from molab.workspace.run import TERMINAL_STATUSES

    status = run.status_label
    if status not in TERMINAL_STATUSES:
        raise ValueError(
            f"run {run.id} is {status!r} — only a terminal run "
            f"({sorted(TERMINAL_STATUSES)}) has an outcome to harvest"
        )
    if not narrative.strip():
        raise ValueError(
            "harvest requires a non-empty narrative — knowledge is interpretation; "
            "the raw record already lives in run.json and the run's artifacts"
        )

    experiment = run.experiment
    item_name = name or f"{slugify(of.__name__)}-{run.id}"
    return write_knowledge(
        experiment,
        name=item_name,
        of=of,
        sources=[
            SourceRef(kind="run", ref=run.id),
            SourceRef(kind="experiment", ref=experiment.id),
        ],
        created_by=created_by,
        text=_render_body(run, cls=of, narrative=narrative, results=results),
        cite=[(run, "derived_from")],
    )


def _render_body(
    run: Run,
    *,
    cls: type[Knowledge],
    narrative: str,
    results: dict[str, JSONValue] | None,
) -> str:
    status = run.status_label
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
