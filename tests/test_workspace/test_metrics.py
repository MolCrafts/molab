"""``molexp.workspace.metrics`` — MolRec metrics JSONL under a run root.

``MetricsWriter`` (``ctx.metrics``) appends to ``metrics/metrics.jsonl`` and
rebuilds the derived ``metrics/index.json`` on flush; ``read_run_metrics``
queries the stream. Layout matches molrec's JSONL reference binding (same as
molnex ``MetricsWriter``). Metrics are run-local section data — never
workspace assets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molexp.workspace.metrics import MetricsWriter, read_run_metrics


class TestMetricsWriter:
    def test_scalar_writes_run_local_files(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.25, step=1)

        metrics_file = Path(run.run_dir) / "metrics" / "metrics.jsonl"
        index_file = Path(run.run_dir) / "metrics" / "index.json"

        assert metrics_file.exists()
        assert index_file.exists()
        assert json.loads(metrics_file.read_text().strip())["k"] == "train/loss"

        index = json.loads(index_file.read_text())
        assert index["line_count"] == 1
        assert index["series_count"] == 1
        assert index["series"]["train/loss"]["latest_step"] == 1

    def test_metrics_are_not_workspace_assets(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.25, step=1)

        from molexp.workspace.assets import scan

        root = run.experiment.project.workspace.root
        assert scan.scan_assets(root, kind="metrics", producer_run=run.id) == []

        manifest = json.loads((Path(run.run_dir) / "assets.json").read_text())
        kinds = {entry["kind"] for entry in manifest["assets"].values()}
        assert "metrics" not in kinds

    def test_index_accumulates_across_writes_and_series(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.3, step=1)
            ctx.metrics.scalar("train/loss", 0.2, step=2)
            ctx.metrics.scalar("eval/acc", 0.8, step=2)

        index = json.loads((Path(run.run_dir) / "metrics" / "index.json").read_text())
        assert index["line_count"] == 3
        assert index["series_count"] == 2
        assert index["series"]["train/loss"]["count"] == 2
        assert index["series"]["train/loss"]["latest_step"] == 2

    def test_invalid_scalar_value_rejected(self, run):
        with run.start() as ctx, pytest.raises(ValueError, match="scalar metric value"):
            ctx.metrics.scalar("train/loss", float("nan"), step=1)


class TestReadRunMetrics:
    def test_filters_by_type_and_key(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.3, step=1)
            ctx.metrics.text("note", "warmup", step=1)
            ctx.metrics.scalar("train/loss", 0.2, step=2)

        result = read_run_metrics(Path(run.run_dir), metric_type="scalar", key="train/loss")

        assert [record["v"] for record in result.records] == [0.3, 0.2]
        assert result.series[0]["key"] == "train/loss"
        assert result.next_offset > 0

    def test_unparseable_lines_are_skipped_and_counted(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.3, step=1)

        metrics_file = Path(run.run_dir) / "metrics" / "metrics.jsonl"
        with metrics_file.open("a", encoding="utf-8") as fh:
            fh.write("{bad json\n")
            fh.write(json.dumps({"t": "scalar", "k": "train/loss", "s": 2, "v": 0.2}))
            fh.write("\n")

        result = read_run_metrics(Path(run.run_dir))

        assert result.parse_errors == 1
        assert [record["v"] for record in result.records] == [0.3, 0.2]
        assert result.next_offset == metrics_file.stat().st_size


class TestIncrementalReads:
    """``since_offset`` follows a growing stream without re-reading it."""

    def _write(self, run_dir: Path, count: int, start: int = 0) -> None:
        writer = MetricsWriter(run_dir)
        for i in range(start, start + count):
            writer.scalar("loss", float(i), step=i)

    def test_offset_cursor_returns_only_new_records(self, tmp_path: Path) -> None:
        self._write(tmp_path, 50)
        first = read_run_metrics(tmp_path)
        self._write(tmp_path, 5, start=50)

        second = read_run_metrics(tmp_path, since_offset=first.next_offset)

        assert [r["v"] for r in second.records] == [50.0, 51.0, 52.0, 53.0, 54.0]

    def test_cursor_advances_past_the_consumed_bytes(self, tmp_path: Path) -> None:
        self._write(tmp_path, 10)
        result = read_run_metrics(tmp_path)
        assert result.next_offset == (tmp_path / "metrics" / "metrics.jsonl").stat().st_size

    def test_offset_seek_skips_reading_earlier_lines(self, tmp_path: Path) -> None:
        self._write(tmp_path, 200)
        whole = read_run_metrics(tmp_path)
        self._write(tmp_path, 1, start=200)

        delta = read_run_metrics(tmp_path, since_offset=whole.next_offset)

        assert len(delta.records) == 1
        assert delta.next_offset > whole.next_offset

    def test_offset_past_eof_restarts_from_the_top(self, tmp_path: Path) -> None:
        self._write(tmp_path, 10)
        result = read_run_metrics(tmp_path, since_offset=10**9)
        assert len(result.records) == 10

    def test_follow_loop_sees_every_record_exactly_once(self, tmp_path: Path) -> None:
        self._write(tmp_path, 37)
        cursor, seen = 0, []
        for _ in range(100):
            page = read_run_metrics(tmp_path, since_offset=cursor, limit=5)
            if page.next_offset == cursor:
                break
            seen += [r["v"] for r in page.records]
            cursor = page.next_offset

        assert seen == [float(i) for i in range(37)]

    def test_line_cursor_is_gone(self, tmp_path: Path) -> None:
        # Only the byte cursor remains; the line cursor was removed outright.
        self._write(tmp_path, 20)
        with pytest.raises(TypeError):
            read_run_metrics(tmp_path, since_line=15)


class TestScanCeiling:
    def test_stops_at_max_scan_bytes_and_reports_truncated(self, tmp_path: Path) -> None:
        writer = MetricsWriter(tmp_path)
        for i in range(500):
            writer.scalar("loss", float(i), step=i)

        result = read_run_metrics(tmp_path, max_scan_bytes=500)

        assert result.truncated
        assert len(result.records) < 500

    def test_truncated_result_can_be_resumed(self, tmp_path: Path) -> None:
        writer = MetricsWriter(tmp_path)
        for i in range(200):
            writer.scalar("loss", float(i), step=i)

        first = read_run_metrics(tmp_path, max_scan_bytes=400)
        second = read_run_metrics(tmp_path, since_offset=first.next_offset)

        values = [r["v"] for r in first.records] + [r["v"] for r in second.records]
        assert values == [float(i) for i in range(200)]

    def test_untruncated_read_reports_false(self, tmp_path: Path) -> None:
        MetricsWriter(tmp_path).scalar("loss", 1.0, step=0)
        assert read_run_metrics(tmp_path).truncated is False
