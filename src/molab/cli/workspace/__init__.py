"""``molab.cli.workspace`` — workspace command implementations.

Command modules (``run`` / ``serve`` / ``monitor`` / ``explore`` / ``sync`` /
``lifecycle`` / ``resources``) register their commands on the shared top-level
app (:mod:`molab.cli._app`); the flat tree is assembled in :mod:`molab.cli`.
This package no longer owns a Typer group or a target-resolving callback —
target resolution moved to :mod:`molab.cli._target`.
"""

from __future__ import annotations

from molab.workspace.target import RemoteTarget


class RemoteWorkspaceError(Exception):
    """Deprecated: remote workspace CRUD now goes through FileSystem.

    Kept so older callers that catch this type still import cleanly. Prefer
    :func:`molab.cli._target.open_workspace` for local/remote parity.
    """

    def __init__(self, target: RemoteTarget | None) -> None:
        super().__init__(
            f"Remote workspace operation failed for {target}. "
            "Workspace open/CRUD now uses the target FileSystem; "
            "this error should not be raised by current CLI paths."
        )
