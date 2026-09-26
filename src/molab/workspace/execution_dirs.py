"""The directories inside one Execution, as peers.

An attempt's directory holds several siblings — scratch, bulk output,
promoted products, scheduler evidence, resumable state. **They are peers.**
Nothing ranks them, no directory gets an accessor the others do not have,
and no caller may special-case one by matching its name.

What a directory *means* is the fields of its :class:`ExecutionDir`
declaration, so the questions callers actually ask are answered by querying
those fields rather than by hard-coding a layout:

===========================================  =============================
question                                     answer
===========================================  =============================
"what goes into the git history?"            ``versioned``
"where should a reader look for results?"    ``products``
"what may a prune remove?"                   ``prunable``
"is this directory name legal here?"         :func:`resolve_execution_dir`
===========================================  =============================

Registration is open: a package that writes a directory declares it, the
same rule that gives molrs the solver formats. molab seeds the five its
own layout law documents; anything else is declared by whoever writes it.

Naming a directory at a *call site* is not privilege — ``get_dir("work")``
and ``get_dir("artifacts")`` are the same call, and a writer naturally knows
which of the three tiers it is producing. Privilege would be one of them
having a bespoke property while the others need a string.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ARTIFACTS",
    "CHECKPOINTS",
    "JOBS",
    "OUT",
    "WORK",
    "ExecutionDir",
    "UnknownExecutionDirError",
    "execution_dir_names",
    "list_execution_dirs",
    "product_dirs",
    "prunable_dirs",
    "register_execution_dir",
    "resolve_execution_dir",
    "scratch_dirs",
]


class UnknownExecutionDirError(KeyError):
    """Asked for a directory nobody declared.

    Raised instead of silently creating one: an undeclared directory is a
    layout nothing validates, nothing versions, and no reader looks in.
    """

    def __init__(self, name: str) -> None:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        super().__init__(f"unknown execution directory {name!r}; declared: {known}")
        self.name = name


@dataclass(frozen=True)
class ExecutionDir:
    """One directory inside an Execution, and what it promises."""

    name: str
    """The directory name, exactly as it appears on disk."""

    purpose: str
    """One line, for a person reading docs or the UI's file tree."""

    versioned: bool
    """True when its contents belong in the workspace's git history.

    False means bulk — reproducible bytes that would make the history
    unusable. The workspace ``.gitignore`` is generated from this field, so
    a new directory cannot be forgotten there.
    """

    products: bool
    """True when a reader looking for results should look here.

    Scratch is False: a half-written intermediate that happens to match a
    reader's pattern must not be charted as if it were a result.
    """

    prunable: bool = False
    """True when a prune may remove this directory from a sealed attempt.

    A *prune* (``molab runs prune``, or ``molab.workspace.prune``) deletes
    an attempt's bulk directories to free disk space and keeps its record,
    ``execution.json``. Only a *sealed* attempt, one that has finished and
    been frozen, is ever pruned. Defaults to False, the safe direction: a
    directory whose declaration does not opt in is always kept.
    ``artifacts/`` is not prunable because ``Artifact.path`` points at its
    bytes.
    """


# ── molab's own three tiers, plus the two the layout law documents ──────
#
# A workflow task writes into ``out/`` (``ctx.task_workdir`` resolves there):
# what a body produces mixes its generated inputs, its intermediates and its
# trajectory, and those cannot be sorted out from the outside — so they land
# in the tier that is *kept*, never the disposable one. ``artifacts/`` is
# reached by promotion, and ``emit_artifact`` promotes from any tier.
#
# ``work/`` is left to the framework's own scratch, which really is
# disposable: plan boards, harness staging, landing copies.

WORK = ExecutionDir(
    name="work",
    purpose="Framework scratch: plan boards, harness staging. Disposable.",
    versioned=False,
    products=False,
    prunable=True,
)

OUT = ExecutionDir(
    name="out",
    purpose="What each task wrote: trajectories, restarts, solver logs, inputs.",
    versioned=False,
    products=True,
    prunable=True,
)

ARTIFACTS = ExecutionDir(
    name="artifacts",
    purpose="Promoted products, registered on the Execution and citable.",
    versioned=True,
    products=True,
)

JOBS = ExecutionDir(
    name="jobs",
    purpose="Scheduler evidence: submit scripts, stdout, stderr.",
    versioned=True,
    products=False,
    prunable=True,
)

CHECKPOINTS = ExecutionDir(
    name="checkpoints",
    purpose="Resumable state a task wrote through ctx.checkpoint.",
    versioned=True,
    products=False,
    prunable=True,
)

_REGISTRY: dict[str, ExecutionDir] = {}
_ORDER: list[str] = []


def register_execution_dir(directory: ExecutionDir) -> None:
    """Declare a directory an Execution may contain.

    Re-registering the same name replaces the declaration — a package
    loaded twice must not raise. Registration order is *lookup* order for
    :func:`product_dirs`, which is a search sequence, not a ranking.
    """
    if directory.name not in _REGISTRY:
        _ORDER.append(directory.name)
    _REGISTRY[directory.name] = directory


def resolve_execution_dir(name: str) -> ExecutionDir:
    """The declaration for *name*, or raise :class:`UnknownExecutionDirError`."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownExecutionDirError(name) from None


def list_execution_dirs() -> tuple[ExecutionDir, ...]:
    """Every declared directory, in registration order."""
    return tuple(_REGISTRY[name] for name in _ORDER)


def execution_dir_names() -> frozenset[str]:
    """Just the names — what a layout validator needs."""
    return frozenset(_REGISTRY)


def product_dirs() -> tuple[ExecutionDir, ...]:
    """Directories a reader should search for results, in lookup order.

    Most-curated first is *registration* order, not status: a promoted
    ``artifacts/`` copy and the raw ``out/`` file it came from are the same
    result, and a searcher wants the registered one.
    """
    return tuple(d for d in list_execution_dirs() if d.products)


def prunable_dirs() -> tuple[ExecutionDir, ...]:
    """Directories a prune may remove from a sealed attempt, in registration order.

    See :attr:`ExecutionDir.prunable` for what a prune is. This is the one
    source of the prunable set. The planner picks candidates from it, and
    ``ExecutionRepository.mark_pruned`` validates against it.

    Returns:
        Every declared directory whose ``prunable`` is True. With molab's own
        seeds these are ``out``, ``work``, ``jobs`` and ``checkpoints``;
        ``artifacts`` is never included.
    """
    return tuple(d for d in list_execution_dirs() if d.prunable)


def scratch_dirs() -> tuple[ExecutionDir, ...]:
    """Directories whose bytes stay out of the history."""
    return tuple(d for d in list_execution_dirs() if not d.versioned)


for _seed in (ARTIFACTS, OUT, WORK, JOBS, CHECKPOINTS):
    register_execution_dir(_seed)
