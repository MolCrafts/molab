"""Dependent-params resolution for per-task node bodies.

When a task declares ``dependent_params=fn``, its config is computed from the
upstream tasks' outputs at run time. This module owns that resolution and the
small upstream-view proxies it hands to ``fn`` — kept apart from the dispatch
core in :mod:`.node`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..protocols import JSONMapping, TaskInput, TaskOutput
from .state import WorkflowState

if TYPE_CHECKING:
    from .._graph_decl import TaskRegistration


class _UpstreamView:
    """Per-upstream view passed to ``dependent_params(prev)``.

    Exposes ``.output``, the upstream task's return value as recorded in
    :attr:`WorkflowState.results`.
    """

    __slots__ = ("output",)

    def __init__(self, output: TaskOutput) -> None:
        self.output = output


def _resolve_dependent_params(
    *,
    registration: TaskRegistration,
    state: WorkflowState,
    base_config: JSONMapping | None,
) -> JSONMapping | None:
    """If the task declares ``dependent_params=fn``, resolve and overlay onto config.

    ``fn`` receives ``dict[str, _UpstreamView]`` keyed by upstream task name.
    Its return mapping is overlayed onto a fresh
    :class:`~molab.profile.ProfileConfig` and the result replaces the task's
    base config. The base config is returned unchanged when no
    ``dependent_params`` is declared.
    """
    fn = getattr(registration, "dependent_params", None)
    if fn is None:
        return base_config

    from molab.profile import ProfileConfig

    prev: dict[str, _UpstreamView] = {}
    for dep in registration.depends_on:
        prev[dep] = _UpstreamView(output=state.results.get(dep))

    overlay = fn(prev)
    if overlay is None:
        return base_config
    if not isinstance(overlay, Mapping):
        raise TypeError(
            f"dependent_params for task {registration.name!r} must return a Mapping; "
            f"got {type(overlay).__name__}"
        )
    merged: dict[str, TaskInput] = dict(base_config) if base_config is not None else {}
    merged.update(overlay)
    return ProfileConfig(merged, name=getattr(base_config, "name", None))
