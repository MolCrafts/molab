"""Health stays answerable while heavy work is in flight (P1-1g).

The failure this guards against is operational, not functional: a few
multi-second scans used to occupy the shared request threads, so an
orchestrator's ``GET /api/health`` timed out and the server was declared down
while it was merely busy. Health is now ``async`` (no I/O, answered on the
event loop) and the scans run on a separate, small pool.
"""

from __future__ import annotations

import inspect
import threading
import time

from fastapi.testclient import TestClient

from molexp.server import executors
from molexp.server.app import create_app


class TestHealthIsAsync:
    def test_health_handler_is_a_coroutine(self) -> None:
        app = create_app()
        route = next(r for r in app.routes if getattr(r, "path", None) == "/api/health")
        assert inspect.iscoroutinefunction(route.endpoint), (
            "a sync health handler runs on the shared worker pool and can queue "
            "behind heavy requests"
        )

    def test_health_answers_while_the_heavy_pool_is_saturated(self) -> None:
        """Both heavy workers blocked — health must still return promptly."""
        release = threading.Event()
        occupied = threading.Barrier(3, timeout=10)

        def _hog() -> None:
            occupied.wait()
            release.wait(timeout=10)

        pool = executors.heavy_executor()
        futures = [pool.submit(_hog) for _ in range(2)]
        try:
            occupied.wait()  # both workers are now parked
            app = create_app()
            with TestClient(app) as client:
                started = time.monotonic()
                response = client.get("/api/health")
                elapsed = time.monotonic() - started
            assert response.status_code == 200
            assert elapsed < 2.0, f"health took {elapsed:.2f}s behind a saturated heavy pool"
        finally:
            release.set()
            for future in futures:
                future.result(timeout=10)


class TestHeavyExecutor:
    def test_pool_is_bounded_and_shared(self) -> None:
        pool = executors.heavy_executor()
        assert pool is executors.heavy_executor()
        assert pool._max_workers == 2, "the heavy pool is deliberately small"

    def test_run_heavy_forwards_args_and_kwargs(self) -> None:
        import asyncio

        def _add(a: int, *, b: int) -> int:
            return a + b

        assert asyncio.run(executors.run_heavy(_add, 1, b=2)) == 3

    def test_shutdown_is_idempotent(self) -> None:
        executors.heavy_executor()
        executors.shutdown_heavy_executor()
        executors.shutdown_heavy_executor()
        assert executors.heavy_executor() is not None
