"""Shared helpers for the molab CLI.

Everything in this module is internal — command modules import from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich import print as rprint
from rich.console import Console

from molab._typing import JSONValue
from molab.plugins.submit_molq.metadata import normalize_executor_info
from molab.workspace import Workspace

if TYPE_CHECKING:
    from molab.workspace.fs import FileSystem

# Zombie-run reaping moved into the workspace layer (run-recovery bug 5) so
# the CLI and the server verbs consult ONE policy; these re-exports keep the
# historical ``molab.cli._common`` import path working.
from molab.workspace.run import Run
from molab.workspace.run_reaper import pid_alive, reap_zombie_run

console = Console()

# Rich color mapping used by list / info / monitor displays.
_STATUS_COLORS: dict[str, str] = {
    "succeeded": "green",
    "failed": "red",
    "running": "yellow",
    "finalizing": "yellow",
    "queued": "blue",
    "pending": "blue",
    "interrupted": "red",
    "cancelled": "gray",
}


def status_color(status: str) -> str:
    """Return the rich color for a run status (white if unknown)."""
    return _STATUS_COLORS.get(str(status).lower(), "white")


def get_workspace(
    path: Path | str | None = None,
    *,
    fs: FileSystem | None = None,
) -> Workspace:
    """Load the workspace at *path* (default: current directory).

    Pass *fs* for remote roots (``RemoteFileSystem``).  Without *fs*, the
    local filesystem is used — the historical local-only behaviour.
    """
    if fs is not None:
        return Workspace(path if path is not None else ".", fs=fs)
    return Workspace(path or Path.cwd())


def deterministic_run_id(params: dict[str, JSONValue]) -> str:
    """Generate a deterministic 16-char run ID from parameters.

    Same parameters always produce the same ID, making run creation
    idempotent across repeated ``molab run`` invocations.  The caller
    decides which fields to include (for profile-aware IDs, mix in
    the profile name / config hash).

    Delegates to :func:`molab.workspace.utils.derive_run_id` — the single
    canonicalization shared with ``Experiment.add_runs`` — keeping this name
    and its 16-char output stable for existing CLI callers.
    """
    from molab.workspace.utils import derive_run_id

    return derive_run_id(params)


def run_executor_info(run: Run) -> dict[str, str]:
    """Return normalized executor metadata from the run's latest Execution.

    The executor facts (backend / scheduler / cluster / job ids) are recorded
    on each attempt's ``execution.json``; this reads the most recent attempt,
    ``run.executions[-1]`` (attempts are ordered by creation). ``run.json`` is
    not consulted — it holds only the run's logical definition.

    Args:
        run: The workspace run to describe.

    Returns:
        The latest Execution's ``executor`` normalized through
        ``normalize_executor_info``, or ``{}`` when the run has no Execution.
    """
    executions = run.executions
    return normalize_executor_info(executions[-1].executor if executions else None, {})


def run_environment(run: Run) -> dict[str, JSONValue]:
    """Return the environment recorded on the run's latest Execution.

    The creation- and start-time facts (profile, config, config_hash,
    script, ...) live on each attempt's ``execution.json``; this reads the
    most recent attempt, ``run.executions[-1]`` (attempts are ordered by
    creation), so a rerun shows the profile it was created with. There is no
    fallback to ``run.json``.

    Args:
        run: The workspace run to describe.

    Returns:
        A shallow copy of the latest Execution's ``environment``, or ``{}``
        when the run has no Execution.
    """
    executions = run.executions
    return dict(executions[-1].environment) if executions else {}


__all__ = [
    "console",
    "deterministic_run_id",
    "get_workspace",
    "pid_alive",
    "reap_zombie_run",
    "rprint",
    "run_environment",
    "run_executor_info",
    "status_color",
]
