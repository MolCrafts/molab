"""Informational wall-clock locks — run only with ``MOLAB_PERF=1``.

Thresholds are deliberately generous (they guard against order-of-magnitude
regressions, not jitter); the hard gates are the syscall budgets.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from .conftest import SynthLayout, make_client

pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(os.environ.get("MOLAB_PERF") != "1", reason="set MOLAB_PERF=1"),
]


def _timed(fn):
    t = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t


class TestTiming:
    def test_workspace_runs_cold_then_warm(self, plain_workspace, scale) -> None:
        client = make_client(plain_workspace)
        cold, t_cold = _timed(lambda: client.get("/api/workspace/runs", params={"limit": 2000}))
        assert cold.status_code == 200
        warm, t_warm = _timed(lambda: client.get("/api/workspace/runs", params={"limit": 2000}))
        assert warm.status_code == 200
        print(f"\nruns list: cold {t_cold:.3f}s warm {t_warm:.3f}s (N={scale.n_runs})")
        assert t_cold < 60.0
        assert t_warm < 10.0

    def test_knowledge_list(self, plain_workspace) -> None:
        client = make_client(plain_workspace)
        resp, t = _timed(lambda: client.get("/api/knowledge"))
        assert resp.status_code == 200
        print(f"\nknowledge list: {t:.3f}s")
        assert t < 30.0

    def test_events_tail(self, plain_workspace) -> None:
        client = make_client(plain_workspace)
        resp, t = _timed(lambda: client.get("/api/events", params={"limit": 50}))
        assert resp.status_code == 200
        print(f"\nevents limit=50: {t:.3f}s")
        assert t < 5.0

    def test_health_while_context_runs(self, plain_workspace, synth: SynthLayout) -> None:
        client = make_client(plain_workspace)
        done = threading.Event()

        def heavy() -> None:
            try:
                client.get("/api/workspace/context")
            finally:
                done.set()

        worker = threading.Thread(target=heavy, daemon=True)
        worker.start()
        time.sleep(0.05)
        resp, t = _timed(lambda: client.get("/api/health"))
        done.wait(120)
        assert resp.status_code == 200
        print(f"\nhealth during context: {t:.3f}s")
        assert t < 5.0
