"""In-process workspace-change broadcast — the SSE change-stream signal source.

The UI used to learn that anything happened by polling: ``/api/runs`` every
three seconds, the activity feed every three seconds, a full workspace refresh
after every mutation. This bus replaces that with a push: a mutation (a run
verb, an asset registration, a knowledge write) publishes a
:class:`WorkspaceChange`, the server's ``GET /api/workspace/events/stream``
re-emits it, and the client invalidates *only* the affected queries.

Relationship to :mod:`molexp.services.approval_notify`
======================================================
Same pattern, two deliberate differences, both forced by the job:

* **Payload-bearing.** Approvals are a ping because the inbox is small and the
  UI always refetches it whole. Targeted invalidation is the entire point
  here, so a change carries what changed (``kind`` + ``ref``).
* **Thread-safe.** Approval emitters run on the event loop. These run on
  anyio worker threads (a sync route handler) and on the read model's refresh
  thread, so publishing hops to each subscriber's loop with
  ``call_soon_threadsafe`` instead of touching its queue directly.

Signal sources, in order of directness:

1. The event spine — :func:`install_workspace_event_observer` registers a
   :func:`molexp.workspace.events.set_workspace_event_observer` hook, so every
   ``run.*`` / ``asset.added`` / ``knowledge.created`` append becomes a change,
   **including appends made by other processes' verbs in this one**.
2. Explicit route calls, for mutations that have no spine event (a project
   delete, a curation, a cache refresh).
3. The read model's sweep, for changes made by *another process* entirely
   (a CLI ``molexp run`` on the same workspace) — detected by ``stat``.

Lives in ``services`` because the emitters are services/route-layer code and
services must never import ``server``; the SSE route is just one subscriber.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from molexp.workspace.events import WorkspaceEvent

__all__ = [
    "ChangeKind",
    "WorkspaceChange",
    "WorkspaceSubscription",
    "close_workspace_subscribers",
    "install_workspace_event_observer",
    "notify_workspace_changed",
    "open_workspace_subscription",
    "reset_workspace_subscribers",
    "subscribe_workspace_changes",
    "uninstall_workspace_event_observer",
    "workspace_root_of",
]

ChangeKind = Literal[
    "run",
    "asset",
    "knowledge",
    "project",
    "experiment",
    "workspace",
    "agent",
    "approval",
    "all",
]
"""What changed, at the granularity the UI's query keys are cut at."""


class WorkspaceChange(BaseModel, frozen=True):
    """One published change — the SSE frame's payload.

    Attributes:
        root: The workspace root the change belongs to (subscribers filter on it).
        kind: Which family of queries is affected.
        ref: The id/path of the changed object, when there is exactly one.
        seq: The event-spine ``seq``, when the change came from the spine.
        project_id / experiment_id / run_id: Narrowing hints so a client can
            invalidate one experiment's run list rather than every list.
            ``run_id`` also lets a run-scoped ``asset`` change target that
            run's asset/file queries.
        versions: The read model's view versions at publication time.
    """

    root: str
    kind: ChangeKind
    ref: str | None = None
    seq: int | None = None
    project_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None
    versions: dict[str, int] = Field(default_factory=dict)


class _Subscriber:
    """One live subscription: a bounded queue bound to its own event loop."""

    __slots__ = ("loop", "queue", "root")

    def __init__(self, root: str, loop: asyncio.AbstractEventLoop) -> None:
        self.root = root
        self.loop = loop
        self.queue: asyncio.Queue[WorkspaceChange | object] = asyncio.Queue(maxsize=64)


_subscribers: set[_Subscriber] = set()
_CLOSED = object()
_closed = False


def _offer(sub: _Subscriber, change: WorkspaceChange) -> None:
    """Enqueue on the subscriber's own loop; collapse a backlog to ``all``.

    A client that cannot keep up must not be able to stall an emitter or grow
    memory, and must not silently miss an invalidation either — so an overflow
    degrades to one coarse ``kind="all"``, which is always *safe* (it
    invalidates more than needed) and never wrong.
    """
    try:
        sub.queue.put_nowait(change)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty):
            while True:
                sub.queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            sub.queue.put_nowait(
                WorkspaceChange(root=change.root, kind="all", versions=change.versions)
            )


def notify_workspace_changed(change: WorkspaceChange) -> None:
    """Publish *change* to every subscriber of its workspace.

    Safe to call from any thread and from a synchronous route handler; never
    blocks and never raises (a dead loop or a closed subscriber is dropped).
    """
    if _closed:
        return
    for sub in list(_subscribers):
        if sub.root != change.root:
            continue
        try:
            sub.loop.call_soon_threadsafe(_offer, sub, change)
        except RuntimeError:
            # The subscriber's loop is gone; its generator will clean itself up.
            _subscribers.discard(sub)


def close_workspace_subscribers() -> None:
    """Wake and end every live subscription (server shutdown hook)."""
    global _closed
    _closed = True
    for sub in list(_subscribers):
        with contextlib.suppress(RuntimeError):
            sub.loop.call_soon_threadsafe(_close_one, sub)


def _close_one(sub: _Subscriber) -> None:
    with contextlib.suppress(asyncio.QueueFull):
        sub.queue.put_nowait(_CLOSED)


def reset_workspace_subscribers() -> None:
    """Test / re-serve helper: clear the closed latch for a new process cycle."""
    global _closed
    _closed = False
    _subscribers.clear()


class WorkspaceSubscription:
    """A live subscription to one workspace's changes.

    Two properties a caller that polls with a timeout depends on, neither of
    which an async generator can offer:

    * **Registered on creation, not on first read.** A generator's body does
      not run until its first ``__anext__``, so a caller that opened one and
      then waited would not be in :data:`_subscribers` while it waited, and a
      change published in that window would go nowhere.
    * **Cancel-safe reads.** :meth:`get` parks on :meth:`asyncio.Queue.get`,
      and cancelling that only drops the waiter — the subscription and any
      queued change survive. Cancelling a generator's ``anext`` instead throws
      into the generator body and runs its ``finally``, which unregisters it:
      one timed-out poll would silently kill the stream.

    So a caller may wrap :meth:`get` in :func:`asyncio.wait_for` to notice a
    shutdown promptly without tearing its own subscription down.
    """

    __slots__ = ("_active", "_sub")

    def __init__(self, root: str) -> None:
        self._sub = _Subscriber(str(root), asyncio.get_running_loop())
        # A subscription opened after shutdown is inert rather than an error:
        # the caller learns by getting ``None`` on its first read.
        self._active = not _closed
        if self._active:
            _subscribers.add(self._sub)

    async def get(self) -> WorkspaceChange | None:
        """Wait for the next change, or ``None`` once the stream is finished.

        Cancellation-safe: a cancelled wait leaves the subscription registered
        and any pending change queued for the next call.
        """
        if not self._active or _closed:
            return None
        item = await self._sub.queue.get()
        if item is _CLOSED or _closed or not isinstance(item, WorkspaceChange):
            return None
        return item

    def close(self) -> None:
        """Unregister. Idempotent, so a ``finally`` may always call it."""
        self._active = False
        _subscribers.discard(self._sub)


def open_workspace_subscription(root: str) -> WorkspaceSubscription:
    """Register a subscription to *root* immediately (see the class docstring)."""
    return WorkspaceSubscription(root)


async def subscribe_workspace_changes(root: str) -> AsyncIterator[WorkspaceChange]:
    """Yield each change published for *root* until disconnect or shutdown.

    The iterator form, for callers that consume with a plain ``async for`` and
    never wait under a timeout. A caller that *does* need a timeout must use
    :func:`open_workspace_subscription` — cancelling a step of this generator
    ends the subscription.
    """
    sub = open_workspace_subscription(root)
    try:
        while True:
            change = await sub.get()
            if change is None:
                return
            yield change
    finally:
        sub.close()


# ── Event-spine bridge ──────────────────────────────────────────────────────

_EVENT_KIND: dict[str, ChangeKind] = {
    "run.created": "run",
    "run.started": "run",
    "run.failed": "run",
    "run.completed": "run",
    "run.cancelled": "run",
    "asset.added": "asset",
    "knowledge.created": "knowledge",
    "workflow.created": "experiment",
    "experiment.created": "experiment",
}


def workspace_root_of(run: Any) -> str | None:  # noqa: ANN401
    """Bus root for *run*'s workspace, or ``None`` when it cannot be reached.

    Subscribers match :attr:`WorkspaceChange.root` by exact string, so an
    emitter deep in a task driver has to spell the root the same way the
    route that opened the stream did — ``str(workspace.resolve())``. This is
    that one spelling, in one place.

    Never raises: a detached or half-built ``Run`` yields ``None`` and the
    caller falls back to the approvals-only ping. Losing a notification is a
    stale tab; raising here would fail a decision that already landed on disk.
    """
    try:
        return str(run.experiment.project.workspace.resolve())
    except Exception:
        return None


def change_from_event(root: str, event: WorkspaceEvent) -> WorkspaceChange:
    """Map a spine event onto a :class:`WorkspaceChange` (pure; unit-tested)."""
    kind = _EVENT_KIND.get(str(event.type), "all")
    ref = event.refs[0] if event.refs else None
    payload = event.payload or {}

    def _str(key: str) -> str | None:
        value = payload.get(key)
        return str(value) if isinstance(value, str | int) else None

    run_id = _str("run_id") or (ref if kind == "run" else None)
    return WorkspaceChange(
        root=root,
        kind=kind,
        ref=ref,
        seq=event.seq,
        project_id=_str("project_id"),
        experiment_id=_str("experiment_id"),
        run_id=run_id,
    )


def install_workspace_event_observer() -> None:
    """Bridge the workspace event spine onto this bus (idempotent).

    Called once at server startup. Every durable spine append — including the
    ones a *different* code path in this process makes — becomes a published
    change, so the stream needs no per-route emit for anything the spine
    already records.
    """
    from molexp.workspace.events import set_workspace_event_observer

    def _observe(root: str, event: WorkspaceEvent) -> None:
        notify_workspace_changed(change_from_event(root, event))

    set_workspace_event_observer(_observe)


def uninstall_workspace_event_observer() -> None:
    """Remove the spine bridge (server shutdown / test isolation)."""
    from molexp.workspace.events import set_workspace_event_observer

    set_workspace_event_observer(None)
