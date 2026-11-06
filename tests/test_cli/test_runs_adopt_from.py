"""``molab runs adopt … --from DIR`` folds a ``molab.track()`` directory (D94).

A script with no molab around it wrote stdout, metrics and staged files
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
    tracker.register(plot, title="loss.png", media_type="image/png")
    tracker.register({"best": 0.2}, title="summary.json")
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
    wal = (attempt / "metrics.mlp.jsonl").read_text(encoding="utf-8")
    assert '"k": "loss"' in wal or '"k":"loss"' in wal
    record = json.loads((attempt / "execution.json").read_text())
    assert record["sealed_at"]
    assert "artifacts" not in record
    assert any(ev["kind"] == "stdout" for ev in record["evidence"])

    from molab.workspace.asset_repository import assets_produced_by
    from molab.workspace.domain import ExecutionOrigin

    ws = Workspace(lab)
    run = ws.get_project("alpha").get_experiment("sweep").get_run(payload["run_id"])
    produced = {
        asset.title: asset
        for asset in assets_produced_by(ws, payload["execution_id"])
        if isinstance(asset.origin, ExecutionOrigin) and asset.origin.run_id == run.id
    }
    assert set(produced) == {"loss.png", "summary.json"}
    assert produced["loss.png"].media_type == "image/png"
    assert "staged_by" not in produced["loss.png"].tags
    assert Path(run.asset_path(produced["loss.png"].id)).read_bytes() == b"\x89PNG"

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


def test_a_bad_manifest_line_refuses_before_the_run_changes(lab: Path, tracked: Path) -> None:
    manifest = tracked / "work" / "_molab" / "staged.jsonl"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
    before = sorted(p.relative_to(tracked) for p in tracked.rglob("*"))
    run = Workspace(lab).get_project("alpha").get_experiment("sweep").add_run(params={"lr": 0.3})

    result = runner.invoke(
        app,
        ["runs", "adopt", "alpha", "sweep", "lr=0.3", "--from", str(tracked), "-ws", str(lab)],
    )
    assert result.exit_code == 1
    assert "not JSON" in result.output
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
