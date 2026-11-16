"""Environment directories: the bytes a workspace holds that are not the experiment.

A virtual environment, Python bytecode and the caches of linters and test
runners are rebuilt from the code. They sit in a workspace only because work
was done there, and they are never a record, a product or an input. This
module finds them and removes them, in the two phases of the prune core
(:mod:`~molab.workspace.prune`) and the scratch clean
(:mod:`~molab.workspace.scratch`):

* :func:`plan_env_clean` walks the workspace and names every directory whose
  name marks an environment (:data:`ENV_DIR_PATTERNS`). It does not descend
  into a match, nor into ``.git`` or ``.molab`` (the history and machine
  state, which own their own bytes). Planning is read-only.
* :func:`apply_env_clean` removes exactly the planned directories, after
  re-checking that each one's name is an environment name.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .workspace import Workspace

__all__ = ["ENV_DIR_PATTERNS", "apply_env_clean", "plan_env_clean"]

#: Directory names that hold an environment or a cache, never the experiment.
ENV_DIR_PATTERNS: tuple[str, ...] = (
    ".venv",
    ".venv-*",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
)

#: Directories the walk never enters: history and machine state.
_SKIP = (".git", ".molab")


def _is_env_name(name: str) -> bool:
    return any(fnmatch(name, pattern) for pattern in ENV_DIR_PATTERNS)


def plan_env_clean(workspace: Workspace) -> tuple[str, ...]:
    """Every environment directory in *workspace*, workspace-relative and sorted. Writes nothing."""
    fs = workspace.fs
    root = str(workspace.root)
    found: list[str] = []
    pending = [root]
    while pending:
        current = pending.pop()
        for entry in fs.ls(current, A=True, l=True):
            # A link is neither entered nor removed: what it points at is not ours.
            if not entry.is_dir or entry.is_symlink or entry.name in _SKIP:
                continue
            path = fs.join(current, entry.name)
            if _is_env_name(entry.name):
                found.append(path[len(root) :].lstrip("/"))
            else:
                pending.append(path)
    return tuple(sorted(found))


def apply_env_clean(workspace: Workspace, plan: tuple[str, ...]) -> int:
    """Remove the directories *plan* names; return how many were removed.

    Raises:
        ValueError: A planned path is not an environment directory; nothing
            is removed.
    """
    refused = [
        rel
        for rel in plan
        if not _is_env_name(rel.rsplit("/", 1)[-1]) or set(rel.split("/")) & set(_SKIP)
    ]
    if refused:
        raise ValueError(f"not an environment directory: {', '.join(refused)}")
    fs = workspace.fs
    removed = 0
    for rel in plan:
        path = fs.join(str(workspace.root), rel)
        if fs.exists(path):
            fs.rm(path, recursive=True)
            removed += 1
    return removed
