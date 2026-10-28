"""``molab runs adopt … --from DIR`` folds a ``molab.track()`` directory (D94).

A script with no molab around it wrote stdout, metrics and staged artifacts
into an offline directory; adopting it gives a sealed attempt carrying them,
timed from the directory's ``track.json``, and the workspace validates clean.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from molab.cli import app
from molab.workspace import Workspace, tracking
from molab.workspace.tracking import TRACK_RECORD, OfflineTracker

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_process_tracker(monkeypatch):
    monkeypatch.setattr(tracking, "_PROCESS", None)


@pytest.fixture
def lab(tmp_path: Path) -> Path:
    ws = Workspace(tmp_path / "lab")
    ws.materialize()
    ws.add_project("alpha").add_experiment("sweep")
    return Path(str(ws.resolve()))


@pytest.fixture
def tracked(tmp_path: Path) -> Path:
    """What ``molab.track(dir)`` left behind in a script outside molab."""
    root = tmp_path / "scratch-run" / "molab-track"
    tracker = OfflineTracker(root)
    tracker.write_stdio("stdout", "epoch 1\nepoch 2\n")
    tracker.metrics.scalar("loss", 0.5, 1)
    tracker.metrics.scalar("loss", 0.2, 2)
    plot = tmp_path / "scratch-run" / "loss.png"
    plot.write_bytes(b"\x89PNG")
    tracker.emit_artifact(plot, media_type="image/png", semantic_type="plot")
    tracker.emit_artifact({"best": 0.2}, name="summary.json")
    tracker.close()
    return root


def test_from_dir_gives_a_sealed_attempt_and_validates_clean(lab: Path, tracked: Path) -> None:
    meta = json.loads((tracked / TRACK_RECORD).read_text())
    result = runner.invoke(
        app,
        [
            "runs", "adopt", "alpha", "sweep", "lr=0.1",
            "--from", str(tracked),
            "--params", '{"lr": 0.1}',
            "--json",
            "-ws", str(lab),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["run_created"] is True
    assert payload["status"] == "succeeded"
    assert datetime.fromisoformat(payload["started_at"]) == datetime.fromisoformat(
        meta["started_at"]
    )
    assert datetime.fromisoformat(payload["finished_at"]) == datetime.fromisoformat(
        meta["finished_at"]
    )

    attempt = lab / payload["path"]
    assert (attempt / "stdout.log").read_text() == "epoch 1\nepoch 2\n"
    record = json.loads((attempt / "execution.json").read_text())
    assert record["sealed_at"]
    by_name = {a["name"]: a for a in record["artifacts"]}
    assert set(by_name) == {"metrics.mlp.jsonl", "loss.png", "summary.json"}
    assert by_name["metrics.mlp.jsonl"]["semantic_type"] == "molplot.metrics"
    assert by_name["loss.png"]["media_type"] == "image/png"
    assert by_name["loss.png"]["metadata"]["staged_by"] == "offline"
    for artifact in record["artifacts"]:
        assert (attempt / artifact["path"]).is_file()
    assert any(ev["kind"] == "stdout" for ev in record["evidence"])

    validate = runner.invoke(app, ["validate", "-ws", str(lab)])
    assert validate.exit_code == 0, validate.output
    assert "conforms" in validate.output


def test_explicit_times_win_over_track_json(lab: Path, tracked: Path) -> None:
    result = runner.invoke(
        app,
        [
            "runs", "adopt", "alpha", "sweep", "lr=0.2",
            "--from", str(tracked),
            "--params", '{"lr": 0.2}',
            "--started", "2026-10-01T10:00:00+00:00",
            "--json",
            "-ws", str(lab),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["started_at"].startswith("2026-10-01T10:00:00")


def test_a_refused_adoption_moves_everything_back(lab: Path, tracked: Path) -> None:
    clash = OfflineTracker(tracked)
    clash.emit_artifact(b"{}", name="metrics.mlp.jsonl")
    clash.close()
    before = sorted(p.relative_to(tracked) for p in tracked.rglob("*"))
    run = Workspace(lab).get_project("alpha").get_experiment("sweep").add_run(params={"lr": 0.3})

    result = runner.invoke(
        app,
        ["runs", "adopt", "alpha", "sweep", "lr=0.3", "--from", str(tracked), "-ws", str(lab)],
    )
    assert result.exit_code == 1
    assert "adopted twice" in " ".join(result.output.split())
    assert sorted(p.relative_to(tracked) for p in tracked.rglob("*")) == before
    assert run.executions == []


def test_a_missing_directory_is_refused(lab: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "runs", "adopt", "alpha", "sweep", "lr=0.4",
            "--from", str(tmp_path / "nope"),
            "--params", '{"lr": 0.4}',
            "-ws", str(lab),
        ],
    )  # fmt: skip
    assert result.exit_code == 1
    assert "not a directory" in " ".join(result.output.split())
