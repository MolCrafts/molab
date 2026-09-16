"""The workspace change bus (P3-3c).

The bus exists so a mutation reaches an open browser tab. Two properties make
that safe rather than merely working: publishing is callable from a **worker
thread** (every sync route handler runs on one), and a subscriber that falls
behind degrades to a coarse ``all`` instead of blocking the emitter or
silently losing an invalidation.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime

import pytest

from molexp.services.workspace_notify import (
    WorkspaceChange,
    change_from_event,
    close_workspace_subscribers,
    install_workspace_event_observer,
    notify_workspace_changed,
    reset_workspace_subscribers,
    subscribe_workspace_changes,
    uninstall_workspace_event_observer,
)
from molexp.workspace.events import WorkspaceEvent


@pytest.fixture(autouse=True)
def _clean_bus():
    reset_workspace_subscribers()
    yield
    uninstall_workspace_event_observer()
    reset_workspace_subscribers()


class TestPublishing:
    @pytest.mark.asyncio
    async def test_subscriber_receives_a_change_for_its_own_root(self) -> None:
        stream = subscribe_workspace_changes("/ws/a")
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        notify_workspace_changed(WorkspaceChange(root="/ws/a", kind="run", ref="r1"))
        change = await asyncio.wait_for(task, timeout=2)
        assert (change.kind, change.ref) == ("run", "r1")

    @pytest.mark.asyncio
    async def test_a_change_for_another_root_is_not_delivered(self) -> None:
        stream = subscribe_workspace_changes("/ws/a")
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        notify_workspace_changed(WorkspaceChange(root="/ws/b", kind="run", ref="other"))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.15)
        task.cancel()

    @pytest.mark.asyncio
    async def test_publish_from_a_worker_thread_reaches_the_subscriber(self) -> None:
        """Every sync route handler runs on a worker thread — this is the real path."""
        stream = subscribe_workspace_changes("/ws/a")
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)

        def _emit() -> None:
            notify_workspace_changed(WorkspaceChange(root="/ws/a", kind="asset", ref="a1"))

        thread = threading.Thread(target=_emit)
        thread.start()
        thread.join()
        change = await asyncio.wait_for(task, timeout=2)
        assert change.kind == "asset"

    @pytest.mark.asyncio
    async def test_overflow_collapses_to_a_single_all(self) -> None:
        stream = subscribe_workspace_changes("/ws/a")
        # Consume one change first: an async generator registers its
        # subscription on the first ``anext``, not at construction.
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        notify_workspace_changed(WorkspaceChange(root="/ws/a", kind="run", ref="warmup"))
        await asyncio.wait_for(task, timeout=2)

        for i in range(200):  # the queue caps at 64
            notify_workspace_changed(WorkspaceChange(root="/ws/a", kind="run", ref=f"r{i}"))
        await asyncio.sleep(0.05)
        nxt = await asyncio.wait_for(anext(stream), timeout=2)
        assert nxt.kind == "all", "a backlogged subscriber must degrade, not lose changes"

    @pytest.mark.asyncio
    async def test_close_ends_the_subscription(self) -> None:
        stream = subscribe_workspace_changes("/ws/a")
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        close_workspace_subscribers()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(task, timeout=2)


def _event(type_: str, refs: list[str] | None = None, **payload: object) -> WorkspaceEvent:
    return WorkspaceEvent(
        id="e1",
        seq=7,
        type=type_,  # type: ignore[arg-type]
        actor="test",
        created_at=datetime.now(UTC),
        payload=payload,  # type: ignore[arg-type]
        refs=refs or [],
    )


class TestEventBridge:
    @pytest.mark.parametrize(
        ("event_type", "expected"),
        [
            ("run.started", "run"),
            ("run.cancelled", "run"),
            ("asset.added", "asset"),
            ("knowledge.created", "knowledge"),
            ("experiment.created", "experiment"),
        ],
    )
    def test_event_type_maps_to_a_change_kind(self, event_type: str, expected: str) -> None:
        change = change_from_event("/ws/a", _event(event_type, ["x1"]))
        assert change.kind == expected
        assert change.ref == "x1"
        assert change.seq == 7

    def test_run_scoped_asset_change_carries_the_run_id(self) -> None:
        """So a client can invalidate that run's file/asset queries, not every list."""
        change = change_from_event("/ws/a", _event("asset.added", ["a1"], run_id="r9"))
        assert (change.kind, change.run_id) == ("asset", "r9")

    @pytest.mark.asyncio
    async def test_installed_observer_publishes_spine_appends(self, tmp_path) -> None:
        from molexp.workspace.events import emit_workspace_event

        root = str(tmp_path)
        install_workspace_event_observer()
        stream = subscribe_workspace_changes(root)
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await asyncio.to_thread(emit_workspace_event, root, "run.completed", "test", refs=["r1"])
        change = await asyncio.wait_for(task, timeout=2)
        assert (change.kind, change.ref) == ("run", "r1")
