"""``/runs/{id}/export`` streams its zip and refuses oversized runs.

The route used to build the whole archive in a ``BytesIO`` before responding,
so exporting a run sized the server's memory to the run.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest


def _touch(run, rel: str, text: str = "x") -> None:
    target = Path(str(run.run_dir)) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def url(project, experiment, run):
    return f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/export"


class TestExportContent:
    def test_streamed_zip_is_valid_and_contains_the_run(self, client, run, url):
        _touch(run, "artifacts/result.dat", "payload")
        _touch(run, "executions/exec-1/stdout.log", "log line\n")

        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert f"run-{run.id}.zip" in resp.headers["content-disposition"]

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            assert zf.testzip() is None
            names = set(zf.namelist())
            assert "artifacts/result.dat" in names
            assert zf.read("artifacts/result.dat") == b"payload"

    def test_stream_matches_the_direct_archive_contents(self, client, run, url):
        """The streamed form must not quietly drop or reorder entries."""
        from molexp.workspace.archive import archive_folder_zip_iter

        _touch(run, "artifacts/a.dat", "aaa")
        _touch(run, "artifacts/nested/b.dat", "bbb")

        streamed = client.get(url).content
        buffered = b"".join(archive_folder_zip_iter(run))
        with (
            zipfile.ZipFile(io.BytesIO(streamed)) as s,
            zipfile.ZipFile(io.BytesIO(buffered)) as b,
        ):
            assert s.namelist() == b.namelist()
            for name in s.namelist():
                assert s.read(name) == b.read(name)


class TestExportLimit:
    def test_oversized_run_is_413_with_the_size(self, client, run, url, monkeypatch):
        # Patch the ceiling rather than writing 2 GB.
        monkeypatch.setattr("molexp.server.routes.run.EXPORT_MAX_BYTES", 10)
        _touch(run, "artifacts/big.dat", "x" * 100)

        resp = client.get(url)
        assert resp.status_code == 413
        detail = resp.json()["detail"]
        assert detail["totalBytes"] >= 100


class TestHeavyPool:
    def test_health_answers_while_the_heavy_pool_is_saturated(self, client):
        """``/api/health`` must never queue behind heavy handlers.

        The heavy pool has two workers; both are blocked here. Health is an
        ``async def`` that touches no filesystem, so it answers regardless.
        """
        import threading

        from molexp.server.executors import run_heavy

        release = threading.Event()
        started = threading.Barrier(3, timeout=10)

        def _block() -> None:
            started.wait()
            release.wait(timeout=10)

        loop_done = threading.Event()

        def _occupy() -> None:
            import asyncio

            async def _main() -> None:
                await asyncio.gather(run_heavy(_block), run_heavy(_block))

            asyncio.run(_main())
            loop_done.set()

        worker = threading.Thread(target=_occupy, daemon=True)
        worker.start()
        try:
            started.wait(timeout=10)  # both heavy workers are now blocked
            resp = client.get("/api/health")
            assert resp.status_code == 200
        finally:
            release.set()
            worker.join(timeout=10)
        assert loop_done.is_set()
