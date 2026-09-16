"""``/runs/{id}/metrics`` follows by byte cursor, not by re-reading from line 0."""

from __future__ import annotations

import pytest

from molexp.workspace.metrics import MetricsWriter


@pytest.fixture
def url(project, experiment, run):
    return f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/metrics"


@pytest.fixture
def writer(run):
    return MetricsWriter(run.run_dir)


class TestCursor:
    def test_next_offset_is_reported(self, client, url, writer):
        writer.scalar("loss", 1.0, step=0)
        body = client.get(url).json()
        assert body["nextOffset"] > 0
        assert len(body["records"]) == 1

    def test_since_offset_returns_only_new_records(self, client, url, writer):
        writer.scalar("loss", 1.0, step=0)
        first = client.get(url).json()

        writer.scalar("loss", 0.5, step=1)
        second = client.get(url, params={"since_offset": first["nextOffset"]}).json()

        assert len(second["records"]) == 1
        assert second["records"][0]["v"] == 0.5
        assert second["nextOffset"] > first["nextOffset"]

    def test_cursor_at_eof_returns_nothing(self, client, url, writer):
        writer.scalar("loss", 1.0, step=0)
        first = client.get(url).json()
        second = client.get(url, params={"since_offset": first["nextOffset"]}).json()
        assert second["records"] == []

    def test_legacy_line_cursor_is_rejected(self, client, url, writer):
        # since_line was removed; an unknown query param must not silently
        # behave like "no cursor" and re-send the whole stream as new data.
        writer.scalar("loss", 1.0, step=0)
        writer.scalar("loss", 0.5, step=1)
        body = client.get(url, params={"since_line": 1}).json()
        assert [r["v"] for r in body["records"]] == [1.0, 0.5]

    def test_scan_budget_reports_truncation(self, client, url, writer):
        for i in range(200):
            writer.scalar("loss", float(i), step=i)
        body = client.get(url, params={"max_scan_bytes": 1024}).json()
        assert body["truncated"] is True
        assert len(body["records"]) < 200

    def test_missing_stream_is_empty_not_an_error(self, client, url):
        body = client.get(url).json()
        assert body["records"] == []
        assert body["truncated"] is False
