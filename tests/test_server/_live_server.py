"""Run the API on a real socket, for the routes that ``TestClient`` cannot test.

``TestClient`` (and ``httpx.ASGITransport`` under it) buffers a response to
completion before handing it back: ``client.stream(...)`` on an endpoint that
stays open never even returns its status line. That makes it structurally
unable to exercise Server-Sent Events, where staying open *is* the contract —
the first ``GET /api/workspace/events/stream`` test written against
``TestClient`` passed only because a bug made the stream hang up after one
second, and started hanging the moment that bug was fixed.

So anything asserting on a live stream runs against uvicorn on a real
ephemeral port, over TCP, which is also the only arrangement where "a change
published while a client is reading reaches that client" says something about
the product rather than about the test rig.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading

import httpx
import uvicorn


def free_port() -> int:
    """An ephemeral port, so concurrent test runs never collide."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LiveServer:
    """A uvicorn server in a background thread, stopped cleanly on exit."""

    def __init__(self, app, port: int | None = None) -> None:
        self.port = port or free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self) -> LiveServer:
        self._thread.start()
        waited, step, deadline = 0.0, 0.05, 30.0
        while waited < deadline:
            with contextlib.suppress(Exception):
                if httpx.get(f"{self.base}/api/health", timeout=1.0).status_code == 200:
                    return self
            threading.Event().wait(step)
            waited += step
        raise RuntimeError("live server did not become ready")

    def __exit__(self, *exc: object) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=15.0)


async def read_sse_frames(
    base: str,
    *,
    params: dict | None = None,
    limit: int = 2,
    timeout: float = 20.0,
) -> list[tuple[str, dict]]:
    """Collect up to *limit* ``event:``/``data:`` pairs from the change stream.

    Returns early on a keep-alive comment, which is the stream stating it has
    nothing further right now — without that, asking for more frames than will
    ever arrive would wait out the whole *timeout*. The timeout is a backstop
    against a stream that never speaks at all, not a pacing mechanism.
    """
    out: list[tuple[str, dict]] = []

    async def _read() -> None:
        event: str | None = None
        async with (
            httpx.AsyncClient(timeout=None) as client,
            client.stream(
                "GET", f"{base}/api/workspace/events/stream", params=params or {}
            ) as response,
        ):
            async for line in response.aiter_lines():
                if line.startswith(":"):
                    return  # idle keep-alive — nothing more is coming
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: ") and event is not None:
                    out.append((event, json.loads(line.removeprefix("data: "))))
                    event = None
                    if len(out) >= limit:
                        return

    import asyncio

    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(_read(), timeout=timeout)
    return out
