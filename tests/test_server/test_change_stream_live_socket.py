"""``GET /api/workspace/events/stream`` over a real socket, against a real server.

Every other test of this route drives the app through ``TestClient`` or
``httpx.ASGITransport``, both of which run the app *inside* the test's own
call. A push that arrives while the client is parked reading is therefore
unobservable: the mutation cannot run until the read returns. That blind spot
hid a bug in which the route polled its subscription with
``asyncio.wait_for(anext(stream), ...)`` — and because ``wait_for`` cancels
what it waits on, and cancelling ``anext`` throws into the generator body and
runs its ``finally``, the subscription unregistered itself one second after
connecting. The stream delivered a ``hello`` and then nothing, forever, while
the browser reconnected in a loop.

So this module runs uvicorn on a real ephemeral port in a background thread and
talks to it over TCP, which is the only arrangement where "a change published
while a client is reading reaches that client" is a statement about the
product rather than about the test harness.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.services import workspace_notify
from molexp.workspace import Workspace

from ._live_server import LiveServer

#: The route's own poll interval; the subscription must outlive several of them.
POLL_SECONDS = 1.0
#: Generous on purpose — this asserts "eventually", never a schedule.
FRAME_TIMEOUT = 15.0


@pytest.fixture
def live_server(tmp_path):
    ws = Workspace(root=tmp_path / "lab", name="lab")
    ws.add_project("proj").add_experiment("exp").add_run(params={"i": 0})
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: ws
    with LiveServer(app) as server:
        yield server


async def _read_frames(base: str, collected: list[str], ready: asyncio.Event) -> None:
    """Stream the change channel, appending every non-blank line to *collected*."""
    async with (
        httpx.AsyncClient(timeout=None) as client,
        client.stream("GET", f"{base}/api/workspace/events/stream") as response,
    ):
        async for line in response.aiter_lines():
            if line.strip():
                collected.append(line)
                if not ready.is_set() and line.startswith("data:"):
                    ready.set()  # the hello frame landed; the stream is live


async def _await_line(collected: list[str], predicate, timeout: float) -> str:
    """Wait until a collected line satisfies *predicate*, or fail the test."""
    waited = 0.0
    while waited < timeout:
        for line in list(collected):
            if predicate(line):
                return line
        await asyncio.sleep(0.05)
        waited += 0.05
    pytest.fail(f"no matching frame within {timeout}s; got {collected!r}")


class TestChangeStreamOverARealSocket:
    async def test_a_mutation_reaches_a_client_that_is_already_reading(self, live_server) -> None:
        """The whole point of the channel: push, not poll.

        Fails before the cancellation fix — the subscription is torn down one
        poll after connecting, so the ``change`` frame is never emitted.
        """
        collected: list[str] = []
        ready = asyncio.Event()
        reader = asyncio.create_task(_read_frames(live_server.base, collected, ready))
        try:
            await asyncio.wait_for(ready.wait(), timeout=FRAME_TIMEOUT)

            # Outlast several poll timeouts: this is the window in which the
            # cancelled-generator bug silently unsubscribed the client.
            await asyncio.sleep(POLL_SECONDS * 2.5)

            async with httpx.AsyncClient(timeout=10.0) as client:
                created = await client.post(
                    f"{live_server.base}/api/projects", json={"name": "pushed"}
                )
            assert created.status_code == 201, created.text

            line = await _await_line(
                collected, lambda ln: ln.startswith("data:") and '"kind"' in ln, FRAME_TIMEOUT
            )
            payload = json.loads(line.removeprefix("data:").strip())
            assert payload["kind"] == "project"
            assert payload["ref"] == "pushed"
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    async def test_the_subscription_survives_its_own_poll_timeouts(self, live_server) -> None:
        """A registered subscriber must still be registered while it waits.

        Asserted directly against the registry rather than through behaviour,
        because "deaf but still connected" is exactly what the bug looked like
        from outside.
        """
        collected: list[str] = []
        ready = asyncio.Event()
        reader = asyncio.create_task(_read_frames(live_server.base, collected, ready))
        try:
            await asyncio.wait_for(ready.wait(), timeout=FRAME_TIMEOUT)
            await asyncio.sleep(POLL_SECONDS * 2.5)
            assert len(workspace_notify._subscribers) == 1, (
                "the stream unregistered itself while still connected"
            )
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader

    async def test_an_idle_stream_stays_open_and_comments(self, live_server, monkeypatch) -> None:
        """Keep-alives only ever appear if the generator is still running.

        The interval is shortened rather than waited out: the point is that a
        comment arrives *after several poll timeouts*, not that it takes 15 s.
        """
        from molexp.server.routes import workspace as workspace_routes

        monkeypatch.setattr(workspace_routes, "_KEEP_ALIVE_SECONDS", 2.0)
        collected: list[str] = []
        ready = asyncio.Event()
        reader = asyncio.create_task(_read_frames(live_server.base, collected, ready))
        try:
            await asyncio.wait_for(ready.wait(), timeout=FRAME_TIMEOUT)
            await _await_line(collected, lambda ln: ln.startswith(":"), FRAME_TIMEOUT)
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
