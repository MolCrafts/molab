"""``GET /api/workspace/events/stream`` — the UI's push channel (P3-3d).

This is what lets the UI stop polling, so the contract the client codes
against is asserted literally: a ``hello`` frame first (carrying the versions
and spine cursor it seeds from), then one ``change`` frame per change, and a
``replayed`` flag that tells a reconnecting client whether it can trust the
deltas or must invalidate its lists once.
"""

from __future__ import annotations

import contextlib

import pytest
from fastapi.testclient import TestClient

from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.workspace import Workspace

from ._live_server import LiveServer, read_sse_frames


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    ws = Workspace(root=tmp_path / "lab", name="lab")
    ws.add_project("proj").add_experiment("exp").add_run(params={"i": 0})
    return ws


@pytest.fixture
def client(workspace: Workspace):
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: workspace
    with TestClient(app) as c:
        yield c


@pytest.fixture
def live(workspace: Workspace, monkeypatch):
    """The stream over a real socket — ``TestClient`` cannot read an open SSE.

    Keep-alives are made immediate so a reader learns "nothing more is coming"
    in one poll instead of fifteen seconds; the interval is right in
    production and merely slow here.
    """
    from molexp.server.routes import workspace as workspace_routes

    monkeypatch.setattr(workspace_routes, "_KEEP_ALIVE_SECONDS", 0.0)
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: workspace
    with LiveServer(app) as server:
        yield server


class TestHelloFrame:
    async def test_stream_opens_with_hello_carrying_versions_and_seq(self, live) -> None:
        kind, payload = (await read_sse_frames(live.base, limit=1))[0]
        assert kind == "hello"
        assert set(payload) == {"versions", "seq", "replayed"}
        assert set(payload["versions"]) == {"runs", "assets", "knowledge"}
        assert isinstance(payload["seq"], int)

    async def test_fresh_connection_without_since_is_not_marked_replayed(self, live) -> None:
        _kind, payload = (await read_sse_frames(live.base, limit=1))[0]
        assert payload["replayed"] is False

    async def test_reconnect_with_since_replays_the_missed_events(
        self, live, workspace: Workspace
    ) -> None:
        """The gap case: a client that was away must not silently miss a change."""
        from molexp.workspace.events import emit_workspace_event

        emit_workspace_event(workspace.root, "run.completed", "test", refs=["r1"])
        frames = await read_sse_frames(live.base, params={"since": 0}, limit=4)

        hello_kind, hello = frames[0]
        assert hello_kind == "hello"
        assert hello["replayed"] is True
        # Frames replay oldest-first; find the one this test emitted (the
        # fixture's ``add_run`` also put a ``run.created`` on the spine).
        refs = {c["ref"] for k, c in frames if k == "change"}
        assert "r1" in refs


class TestLiveChanges:
    """What a mutating route publishes onto the bus the stream re-emits.

    Asserted against the bus rather than through an open SSE response, because
    ``TestClient`` buffers a response to completion and so cannot read a stream
    that stays open. That keeps these cheap and focused on *payload shape* —
    that a cancel carries the parent ids a client needs to invalidate one
    experiment's run list.

    The end-to-end claim these cannot make — a change published while a client
    is reading actually reaches that client — is covered over a real socket in
    ``test_change_stream_live_socket.py``.
    """

    @pytest.mark.asyncio
    async def test_a_mutating_route_publishes_a_run_change(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        import asyncio

        from molexp.services.workspace_notify import subscribe_workspace_changes

        run = workspace.get_project("proj").get_experiment("exp").list_runs()[0]
        url = f"/api/projects/proj/experiments/exp/runs/{run.id}/cancel"

        stream = subscribe_workspace_changes(str(workspace.resolve()))
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        response = await asyncio.to_thread(client.post, url)
        assert response.status_code == 200

        # Two publishes reach the bus for one cancel: the spine observer's
        # (from the durable ``run.cancelled`` event) and the route's own,
        # which adds the parent ids. Both name the same run.
        changes = [await asyncio.wait_for(task, timeout=5)]
        with contextlib.suppress(TimeoutError):
            changes.append(await asyncio.wait_for(anext(stream), timeout=2))

        assert {c.kind for c in changes} == {"run"}
        assert all(c.ref == run.id for c in changes)
        assert any(c.run_id == run.id for c in changes)
        located = [c for c in changes if c.project_id is not None]
        assert located and located[0].experiment_id == "exp", (
            "the route publish must carry the parent ids so a client can "
            "invalidate one experiment's run list"
        )

    @pytest.mark.asyncio
    async def test_a_knowledge_write_publishes_a_knowledge_change(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        import asyncio

        from molexp.services.workspace_notify import subscribe_workspace_changes

        stream = subscribe_workspace_changes(str(workspace.resolve()))
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        response = await asyncio.to_thread(client.post, "/api/knowledge/doc", json={"name": "idea"})
        assert response.status_code == 201, response.text

        change = await asyncio.wait_for(task, timeout=5)
        assert change.kind == "knowledge"


class TestRouteSurface:
    def test_stream_is_published_in_the_openapi_schema(self, client: TestClient) -> None:
        paths = client.get("/api/openapi.json").json()["paths"]
        assert "/api/workspace/events/stream" in paths


class TestReplayTruncation:
    """A backlog longer than the cap must never be sold as a complete delta.

    The spine reads newest-first, so a capped read drops the *oldest* events
    after ``since`` — a hole in the middle of the delta, not a short tail.
    Pairing that with ``replayed: true`` is the silent-staleness bug these
    tests exist to prevent: the client would apply the surviving frames,
    believe itself current, and never refetch.
    """

    @staticmethod
    def _emit(workspace: Workspace, count: int) -> None:
        from molexp.workspace.events import emit_workspace_event

        for i in range(count):
            emit_workspace_event(workspace.root, "run.completed", "test", refs=[f"r{i}"])

    async def test_backlog_over_the_cap_is_reported_as_not_replayed(
        self, live, workspace: Workspace
    ) -> None:
        from molexp.server.routes.workspace import _REPLAY_LIMIT

        self._emit(workspace, _REPLAY_LIMIT + 5)
        frames = await read_sse_frames(live.base, params={"since": 0}, limit=2)

        kind, hello = frames[0]
        assert kind == "hello"
        assert hello["replayed"] is False, (
            "a truncated backlog claimed to be a complete replay — the client "
            "would trust partial deltas and serve stale data"
        )

    async def test_backlog_over_the_cap_sends_no_partial_change_frames(
        self, live, workspace: Workspace
    ) -> None:
        """Not-replayed means the client invalidates; partial frames are waste."""
        from molexp.server.routes.workspace import _REPLAY_LIMIT

        self._emit(workspace, _REPLAY_LIMIT + 5)
        # Ask for more than one frame; a keep-alive ends the read if the
        # server correctly has nothing more to say.
        frames = await read_sse_frames(live.base, params={"since": 0}, limit=3)

        assert [k for k, _ in frames] == ["hello"], (
            f"expected hello only, got {[k for k, _ in frames]}"
        )

    async def test_backlog_at_exactly_the_cap_still_replays_in_full(
        self, live, workspace: Workspace
    ) -> None:
        """The boundary is inclusive: cap events fit, so they are delivered."""
        from molexp.server.routes.workspace import _REPLAY_LIMIT
        from molexp.workspace.events import read_workspace_events

        # The fixture's ``add_run`` already seeded the spine, so measure the
        # cursor first and emit exactly ``_REPLAY_LIMIT`` after it.
        since = max((e.seq for e in read_workspace_events(workspace.root, limit=1)), default=0)
        self._emit(workspace, _REPLAY_LIMIT)

        frames = await read_sse_frames(live.base, params={"since": since}, limit=2)

        kind, hello = frames[0]
        assert kind == "hello"
        assert hello["replayed"] is True
        assert frames[1][0] == "change"
