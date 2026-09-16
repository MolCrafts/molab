"""``GET /api/workspace/events/stream`` — the UI's push channel (P3-3d).

This is what lets the UI stop polling, so the contract the client codes
against is asserted literally: a ``hello`` frame first (carrying the versions
and spine cursor it seeds from), then one ``change`` frame per change, and a
``replayed`` flag that tells a reconnecting client whether it can trust the
deltas or must invalidate its lists once.
"""

from __future__ import annotations

import contextlib
import json

import pytest
from fastapi.testclient import TestClient

from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.workspace import Workspace


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


def _frames(response, limit: int = 2) -> list[tuple[str, dict]]:
    """Parse up to *limit* SSE ``event:``/``data:`` pairs from a live response."""
    out: list[tuple[str, dict]] = []
    event: str | None = None
    for raw in response.iter_lines():
        line = raw if isinstance(raw, str) else raw.decode()
        if line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("data: ") and event is not None:
            out.append((event, json.loads(line[len("data: ") :])))
            event = None
            if len(out) >= limit:
                break
    return out


class TestHelloFrame:
    def test_stream_opens_with_hello_carrying_versions_and_seq(self, client: TestClient) -> None:
        with client.stream("GET", "/api/workspace/events/stream") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            kind, payload = _frames(response, limit=1)[0]
        assert kind == "hello"
        assert set(payload) == {"versions", "seq", "replayed"}
        assert set(payload["versions"]) == {"runs", "assets", "knowledge"}
        assert isinstance(payload["seq"], int)

    def test_fresh_connection_without_since_is_not_marked_replayed(
        self, client: TestClient
    ) -> None:
        with client.stream("GET", "/api/workspace/events/stream") as response:
            _kind, payload = _frames(response, limit=1)[0]
        assert payload["replayed"] is False

    def test_reconnect_with_since_replays_the_missed_events(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        """The gap case: a client that was away must not silently miss a change."""
        from molexp.workspace.events import emit_workspace_event

        emit_workspace_event(workspace.root, "run.completed", "test", refs=["r1"])
        with client.stream("GET", "/api/workspace/events/stream", params={"since": 0}) as response:
            frames = _frames(response, limit=4)

        hello_kind, hello = frames[0]
        assert hello_kind == "hello"
        assert hello["replayed"] is True
        # Frames replay oldest-first; find the one this test emitted (the
        # fixture's ``add_run`` also put a ``run.created`` on the spine).
        refs = {c["ref"] for k, c in frames if k == "change"}
        assert "r1" in refs


class TestLiveChanges:
    """What a mutating route publishes onto the bus the stream re-emits.

    Asserted against the bus rather than through an open SSE response: the
    in-process test transports serialize the app and the test, so a push that
    happens *while* a stream is being read cannot be observed there. The frame
    encoding those changes go through is covered by the replay tests above,
    and bus delivery itself by ``tests/test_services/test_workspace_notify``.
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

    def test_backlog_over_the_cap_is_reported_as_not_replayed(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        from molexp.server.routes.workspace import _REPLAY_LIMIT

        self._emit(workspace, _REPLAY_LIMIT + 5)
        with client.stream("GET", "/api/workspace/events/stream", params={"since": 0}) as response:
            frames = _frames(response, limit=2)

        kind, hello = frames[0]
        assert kind == "hello"
        assert hello["replayed"] is False, (
            "a truncated backlog claimed to be a complete replay — the client "
            "would trust partial deltas and serve stale data"
        )

    def test_backlog_over_the_cap_sends_no_partial_change_frames(
        self, client: TestClient, workspace: Workspace
    ) -> None:
        """Not-replayed means the client invalidates; partial frames are waste."""
        from molexp.server.routes.workspace import _REPLAY_LIMIT

        self._emit(workspace, _REPLAY_LIMIT + 5)
        with client.stream("GET", "/api/workspace/events/stream", params={"since": 0}) as response:
            # Ask for more than one frame; a keep-alive ends the read if the
            # server correctly has nothing more to say.
            frames = _frames(response, limit=3)

        assert [k for k, _ in frames] == ["hello"], (
            f"expected hello only, got {[k for k, _ in frames]}"
        )

    def test_backlog_at_exactly_the_cap_still_replays_in_full(
        self, tmp_path, workspace: Workspace
    ) -> None:
        """The boundary is inclusive: cap events fit, so they are delivered."""
        from molexp.server.app import create_app
        from molexp.server.dependencies import get_workspace
        from molexp.server.routes.workspace import _REPLAY_LIMIT
        from molexp.workspace.events import read_workspace_events

        # The fixture's ``add_run`` already seeded the spine, so measure the
        # cursor first and emit exactly ``_REPLAY_LIMIT`` after it.
        since = max((e.seq for e in read_workspace_events(workspace.root, limit=1)), default=0)
        self._emit(workspace, _REPLAY_LIMIT)

        app = create_app()
        app.dependency_overrides[get_workspace] = lambda: workspace
        with (
            TestClient(app) as c,
            c.stream("GET", "/api/workspace/events/stream", params={"since": since}) as response,
        ):
            frames = _frames(response, limit=2)

        kind, hello = frames[0]
        assert kind == "hello"
        assert hello["replayed"] is True
        assert frames[1][0] == "change"
