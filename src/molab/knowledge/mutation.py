"""One knowledge verb = one locked change plus one history commit.

Every verb that changes a document on disk (``write`` / ``rename`` /
``move_to`` / ``delete`` / ``append_link`` / ``mutate_relation`` /
``replace_record`` / ``write_knowledge``) runs its body inside
:func:`mutation`, so the CLI, the server and a Python caller all take the same
lock and leave the same commit. A verb called from inside another verb (the
``write`` that ``append_link`` does, the links ``rename`` rewrites) joins the
outer one: it takes no second lock (the lock is not reentrant) and records no
commit of its own, so one user action is one fact in ``git log``.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .concept import Concept

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Mutation:
    """The verb in progress: its workspace root and the other paths it wrote."""

    root: Path | None
    touched: list[str] = field(default_factory=list)


_ACTIVE: ContextVar[Mutation | None] = ContextVar("molab_knowledge_mutation", default=None)


@contextmanager
def mutation(doc: Concept, event: str, summary: str) -> Generator[Mutation]:
    """Run one verb on *doc* under its lock, then commit it to the history.

    The lock is the workspace's per-record lock
    (:func:`molab.workspace.entity_record.record_lock`) keyed by *doc*'s path
    when the verb starts, under the enclosing workspace's ``.molab/locks``;
    outside a workspace, or on a non-local disk, the verb runs unlocked.

    After the body, one :meth:`molab.workspace.GitHistory.record` commit names
    *doc*'s path before and after the verb, the paths the body appended to
    :attr:`Mutation.touched`, and the ``index.md`` of every host those paths
    sit under. A body that raises records nothing.

    **A history failure never fails the verb** (the git commit never blocks
    the science). The files are already written when the commit runs. Any
    exception from the commit is logged as a warning with its traceback and
    not raised; the uncommitted files are picked up by the next commit
    (``molab history sync``).

    Args:
        doc: The document the verb changes.
        event: The ``Molab-Event`` trailer, e.g. ``knowledge.moved``.
        summary: The commit headline.

    Yields:
        The verb in progress; a nested verb yields the outer one.
    """
    outer = _ACTIVE.get()
    if outer is not None:
        yield outer
        return
    from molab.workspace.entity_record import record_lock

    from .location import enclosing_workspace_root

    before = str(doc.path)
    change = Mutation(root=enclosing_workspace_root(before, fs=doc.fs))
    token = _ACTIVE.set(change)
    try:
        with record_lock(doc.fs, before, change.root):
            yield change
    finally:
        _ACTIVE.reset(token)
    if change.root is None:
        return
    try:
        _commit(doc, change.root, event, summary, (before, str(doc.path), *change.touched))
    except Exception:
        _LOG.warning(
            f"history commit {event} for {doc.path} failed; the file is written "
            "and the next commit records it",
            exc_info=True,
        )


def _commit(doc: Concept, root: Path, event: str, summary: str, documents: tuple[str, ...]) -> None:
    """Record *event* for *doc* with *documents* and their hosts' ``index.md``."""
    from molab.workspace.entity_record import INDEX_FILENAME
    from molab.workspace.history import EntityRef, GitHistory

    from .location import host_of

    paths = list(dict.fromkeys(documents))
    for path in tuple(paths):
        host_index = doc.fs.join(str(host_of(path)), INDEX_FILENAME)
        if host_index not in paths and doc.fs.is_file(host_index):
            paths.append(host_index)
    rel = Path(str(doc.path)).relative_to(Path(str(root))).as_posix()
    GitHistory(str(root)).record(
        event,
        subject=EntityRef(id=rel, type=type(doc).__name__),
        summary=summary,
        paths=tuple(paths),
    )


__all__ = ["Mutation", "mutation"]
