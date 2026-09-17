"""``molab.plugins.metrics.wal`` — JSONL-only host metrics under a run.

``MetricsWriter`` (``ctx.metrics``) appends to
``executions/eNN/out/metrics.mlp.jsonl``. ``flush()`` does not densify.
``read_run_metrics`` reads JSONL. Metrics are run-local — never workspace
assets, never ``metrics.mlp.zarr`` / ``metrics.mlp.index.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from molab.plugins.metrics import (
    MetricsWriter,
    read_run_metrics,
)
from molab.workspace.execution_dirs import ARTIFACTS


def _exec_dir(run) -> Path:
    executions = run.executions
    assert executions
    return Path(run.run_dir) / "executions" / executions[-1].id


def _products_wal(root: Path) -> Path:
    return root / ARTIFACTS.name / "metrics.mlp.jsonl"


def _assert_no_zarr_or_index(root: Path) -> None:
    assert not (root / "metrics.mlp.zarr").exists()
    assert not (root / "metrics.mlp.index.json").exists()
    assert not (root / ARTIFACTS.name / "metrics.mlp.zarr").exists()
    assert not (root / ARTIFACTS.name / "metrics.mlp.index.json").exists()


class TestMetricsWriter:
    def test_scalar_writes_run_local_files(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.25, step=1)

        root = _exec_dir(run)
        # One location for both writers. They used to disagree — the
        # execution context wrote into scratch while the run context wrote
        # into products, so a WAL could land where nothing looked.
        metrics_file = _products_wal(root)

        assert metrics_file.is_file()
        assert not (root / "metrics.mlp.jsonl").exists()
        _assert_no_zarr_or_index(root)

        record = json.loads(metrics_file.read_text().strip())
        assert record["k"] == "train/loss"
        assert record["v"] == 0.25
        assert record["s"] == 1

    def test_metrics_are_not_workspace_assets(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.25, step=1)

        from molab.workspace.assets import scan

        root = run.experiment.project.workspace.root
        assert scan.scan_assets(root, kind="metrics", producer_run=run.id) == []

        manifest_path = _exec_dir(run) / "assets.json"
        entries: list[dict[str, object]] = []
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            entries = list(manifest.get("assets", {}).values())
        kinds = {entry["kind"] for entry in entries}
        names = {entry.get("name") for entry in entries}
        assert "metrics" not in kinds
        assert "metrics.mlp.jsonl" not in names

    def test_invalid_scalar_value_rejected(self, run):
        with run.start() as ctx, pytest.raises(ValueError, match="scalar metric value"):
            ctx.metrics.scalar("train/loss", float("nan"), step=1)


class TestReadRunMetrics:
    def test_filters_by_type_key_from_jsonl(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.3, step=1)
            ctx.metrics.text("note", "warmup", step=1)
            ctx.metrics.scalar("train/loss", 0.2, step=2)

        result = read_run_metrics(Path(run.run_dir), metric_type="scalar", key="train/loss")
        assert len(result.records) == 2
        assert [r["v"] for r in result.records] == [0.3, 0.2]
        assert result.series[0]["key"] == "train/loss"

    def test_since_line_uses_wal_for_live_tail(self, run):
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.3, step=1)
            ctx.metrics.scalar("train/loss", 0.2, step=2)

        result = read_run_metrics(
            Path(run.run_dir), metric_type="scalar", key="train/loss", since_line=1
        )
        assert result.next_line == 2
        assert len(result.records) == 1
        assert result.records[0]["v"] == 0.2

    def test_unparseable_lines_are_skipped_and_counted(self, tmp_path: Path):
        writer = MetricsWriter(tmp_path)
        writer.scalar("train/loss", 0.3, step=1)
        metrics_file = _products_wal(tmp_path)
        assert metrics_file.is_file()
        with metrics_file.open("a", encoding="utf-8") as fh:
            fh.write("{bad json\n")
            fh.write(json.dumps({"t": "scalar", "k": "train/loss", "s": 2, "v": 0.2}))
            fh.write("\n")
        result = read_run_metrics(tmp_path)
        assert result.parse_errors == 1
        assert [record["v"] for record in result.records] == [0.3, 0.2]
        assert result.next_line == 3


class TestLogMany:
    """Bulk append path — one open for the whole stream."""

    def test_appends_every_record(self, tmp_path: Path) -> None:
        writer = MetricsWriter(tmp_path)
        written = writer.log_many(
            {"t": "scalar", "k": "train/loss", "s": i, "v": float(i)} for i in range(5)
        )
        assert written == 5
        wal = _products_wal(tmp_path)
        assert wal.is_file()
        assert not (tmp_path / "metrics.mlp.jsonl").exists()
        lines = wal.read_text().splitlines()
        assert len(lines) == 5
        writer.flush()
        _assert_no_zarr_or_index(tmp_path)

    def test_applies_batch_tags_to_every_record(self, tmp_path: Path) -> None:
        writer = MetricsWriter(tmp_path)
        writer.log_many([{"t": "scalar", "k": "a", "v": 1.0}], tags={"src": "bulk"})
        record = json.loads(_products_wal(tmp_path).read_text().strip())
        assert record["tags"] == {"src": "bulk"}

    def test_a_stream_that_raises_first_creates_nothing(self, tmp_path: Path) -> None:
        """No empty buffer left behind — callers treat its presence as truth."""

        def exploding():
            raise RuntimeError("upstream parser died")
            yield  # pragma: no cover

        writer = MetricsWriter(tmp_path)
        with pytest.raises(RuntimeError):
            writer.log_many(exploding())
        assert not _products_wal(tmp_path).exists()
        assert not (tmp_path / "metrics.mlp.jsonl").exists()

    def test_validates_each_record(self, tmp_path: Path) -> None:
        writer = MetricsWriter(tmp_path)
        with pytest.raises(ValueError):
            writer.log_many([{"t": "scalar", "k": "", "v": 1.0}])
