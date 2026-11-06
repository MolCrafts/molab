"""``ctx.metrics`` of an execution: the five record types, ``image`` and the task tag (D93).

``ExecutionContext.metrics`` is a ``TrackedMetrics`` over the attempt's one
WAL writer. These tests pin the round trip through ``read_run_metrics``, the
archived ``image``, the ``molplot.metrics`` registration for any record type,
UTC wall times, the per-task capture the node cache takes, and the in-memory
``BufferedMetrics``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from molab.plugins.metrics import read_run_metrics
from molab.workspace import tracking
from molab.workspace.metrics_seam import MetricRecord
from molab.workspace.tracking import BufferedMetrics, TrackedMetrics, current_task

_PNG = b"\x89PNG\r\n\x1a\nfake"


def _write_all_types(metrics) -> None:
    metrics.scalar("loss", 0.5, 1)
    metrics.histogram("forces", [0.0, 0.5, 1.0], [3, 4], 1)
    metrics.text("note", "converged", 1)
    metrics.image_ref("snapshot", "out/a.png", 1, caption="frame")
    metrics.json("config", {"lr": 0.001, "layers": [64, 64]}, 1)


def _by_type(records: list[MetricRecord]) -> dict[str, MetricRecord]:
    return {str(record["t"]): record for record in records}


class TestRoundTrip:
    def test_five_types_from_run_start(self, run) -> None:
        with run.start() as ctx:
            assert isinstance(ctx.metrics, TrackedMetrics)
            _write_all_types(ctx.metrics)
            execution_dir = ctx.execution_dir
        records = _by_type(read_run_metrics(execution_dir).records)
        assert set(records) == {"scalar", "histogram", "text", "image_ref", "json"}
        assert records["scalar"]["v"] == 0.5
        assert records["histogram"]["v"] == {"bins": [0.0, 0.5, 1.0], "counts": [3, 4]}
        assert records["text"]["v"] == "converged"
        assert records["image_ref"]["v"] == {"path": "out/a.png", "caption": "frame"}
        assert records["json"]["v"] == {"lr": 0.001, "layers": [64, 64]}
        # Outside a task no task tag is added.
        assert all("tags" not in record for record in records.values())

    def test_default_wall_time_is_utc(self, run) -> None:
        with run.start() as ctx:
            record = ctx.metrics.scalar("loss", 1.0)
        stamp = datetime.fromisoformat(str(record["w"]))
        assert stamp.utcoffset() is not None
        assert stamp.utcoffset().total_seconds() == 0

    def test_register_metric_keeps_its_call_style(self, run) -> None:
        with run.start() as ctx:
            record = ctx.register_metric("score", 0.87, step=2, tags={"split": "val"})
        assert record["t"] == "scalar"
        assert record["tags"] == {"split": "val"}


def _image_asset(run, title: str):
    from molab.workspace.asset_repository import assets_produced_by

    produced = assets_produced_by(run.experiment.project.workspace, run.executions[-1].id)
    return next(asset for asset in produced if asset.title == title)


class TestMetricsWal:
    def test_a_histogram_writes_the_wal_and_not_an_asset(self, run) -> None:
        from molab.workspace.asset_repository import assets_produced_by

        with run.start() as ctx:
            ctx.metrics.histogram("forces", [0.0, 1.0], [2])
            execution_dir = ctx.execution_dir
        assert (execution_dir / "metrics.mlp.jsonl").is_file()
        assert assets_produced_by(run.experiment.project.workspace, run.executions[-1].id) == []

    def test_nothing_is_written_when_no_record_is(self, run) -> None:
        with run.start() as ctx:
            assert ctx.metrics.touched is False
            execution_dir = ctx.execution_dir
        assert not (execution_dir / "metrics.mlp.jsonl").exists()


class TestImage:
    def test_bytes_become_an_asset_and_a_ref(self, run) -> None:
        with run.start() as ctx:
            record = ctx.metrics.image("rdf", _PNG, 3, caption="g(r)", name="rdf-3.png")
            execution_dir = ctx.execution_dir
        asset = _image_asset(run, "rdf-3.png")
        assert asset.media_type == "image/png"
        assert record["t"] == "image_ref"
        assert record["v"] == {"path": asset.ref, "caption": "g(r)"}
        workspace = run.experiment.project.workspace
        payload = Path(workspace.assets_at(asset.scope).payload_path(asset.id)).read_bytes()
        assert payload == _PNG
        (on_disk,) = read_run_metrics(execution_dir, metric_type="image_ref").records
        assert on_disk["v"] == record["v"]

    def test_a_path_outside_the_attempt_is_registered(self, run, tmp_path) -> None:
        image = tmp_path / "plot.png"
        image.write_bytes(_PNG)
        with run.start() as ctx:
            record = ctx.metrics.image("plot", image)
        asset = _image_asset(run, "plot.png")
        assert asset.media_type == "image/png"
        assert record["v"] == {"path": asset.ref, "caption": None}

    def test_a_path_inside_the_attempt_is_registered(self, run) -> None:
        with run.start() as ctx:
            image = ctx.task_workdir("plot") / "frame.png"
            image.write_bytes(_PNG)
            record = ctx.metrics.image("frame", image)
        assert image.read_bytes() == _PNG
        asset = _image_asset(run, "frame.png")
        assert record["v"] == {"path": asset.ref, "caption": None}

    def test_bad_data_raises(self, run) -> None:
        with run.start() as ctx:
            with pytest.raises(ValueError, match="name is required"):
                ctx.metrics.image("x", _PNG)
            with pytest.raises(ValueError, match="not an existing file"):
                ctx.metrics.image("x", "no/such/file.png")


class TestTaskTag:
    def test_task_scope_tags_and_captures(self, run) -> None:
        with run.start() as ctx:
            with tracking.task_scope("train"):
                ctx.metrics.scalar("loss", 1.0, 0)
                ctx.metrics.text("note", "hi", tags={"task": "explicit", "x": 1})
            ctx.metrics.scalar("loss", 2.0, 1)
            captured = ctx.metrics.take_task_records("train")
            assert ctx.metrics.take_task_records("train") == []
            execution_dir = ctx.execution_dir
        records = read_run_metrics(execution_dir).records
        assert records[0]["tags"] == {"task": "train"}
        # An explicit ``tags["task"]`` wins over the scope.
        assert records[1]["tags"] == {"task": "explicit", "x": 1}
        assert "tags" not in records[2]
        assert captured == records[:2]

    def test_cap_drops_the_task_and_marks_it_incomplete(self, run, monkeypatch) -> None:
        monkeypatch.setattr(tracking, "TASK_RECORD_CAP", 3)
        with run.start() as ctx:
            with tracking.task_scope("big"):
                for step in range(5):
                    ctx.metrics.scalar("loss", float(step), step)
            with tracking.task_scope("small"):
                ctx.metrics.scalar("loss", 1.0)
            assert ctx.metrics.take_task_records("big") is None
            assert ctx.metrics.take_task_records("big") == []
            assert len(ctx.metrics.take_task_records("small") or []) == 1
            execution_dir = ctx.execution_dir
        # The WAL itself keeps every record.
        assert len(read_run_metrics(execution_dir).records) == 6

    def test_replay_keeps_w_and_s_and_adds_replayed_from(self, run) -> None:
        recorded: MetricRecord = {
            "t": "scalar",
            "k": "loss",
            "s": 7,
            "w": "2026-01-01T00:00:00",
            "v": 0.25,
            "tags": {"task": "train"},
        }
        with run.start() as ctx:
            assert ctx.metrics.replay([recorded], replayed_from="e01") == 1
            assert ctx.metrics.take_task_records("train") == []
            execution_dir = ctx.execution_dir
        (record,) = read_run_metrics(execution_dir).records
        assert record == {**recorded, "tags": {"task": "train", "replayed_from": "e01"}}
        assert recorded["tags"] == {"task": "train"}
        from molab.workspace.asset_repository import assets_produced_by

        assert assets_produced_by(run.experiment.project.workspace, run.executions[-1].id) == []

    def test_a_nested_execution_starts_with_no_task(self, experiment) -> None:
        outer_run = experiment.add_run(params={"n": 1})
        inner_run = experiment.add_run(params={"n": 2})
        with outer_run.start(), tracking.task_scope("outer_task"):
            with inner_run.start() as inner:
                assert current_task() is None
                record = inner.metrics.scalar("x", 1.0)
            assert current_task() == "outer_task"
        assert "tags" not in record


class TestBufferedMetrics:
    def test_collects_records_in_memory(self) -> None:
        metrics = BufferedMetrics()
        _write_all_types(metrics)
        with tracking.task_scope("fit"):
            metrics.image("snap", b"bytes", 2, name="snap.png", caption="c")
        metrics.flush()
        types = [record["t"] for record in metrics.records]
        assert types == ["scalar", "histogram", "text", "image_ref", "json", "image_ref"]
        assert metrics.records[-1]["v"] == {"path": "snap.png", "caption": "c"}
        assert metrics.records[-1]["tags"] == {"task": "fit"}
        assert metrics.records[0]["s"] == 1
