"""On-open runs once per link. Interval waits. A busy mirror skips the tick."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.deps.resolution import _ensure_remote_ready
from molab.server.sync_schedule import SyncSchedule, ensure_sync_schedule, stop_sync_schedules
from molab.workspace.fs_cached import CachedRemoteFileSystem
from molab.workspace.sync_rules import exclusive_transfer, record_result, upsert_rule


class _Fs:
    def __init__(self, mirror) -> None:
        self.mirror_root = mirror
        self.calls: list[str] = []

    def rsync(self, remote: str, **kwargs: object) -> dict[str, str]:
        self.calls.append(remote)
        return {"output": remote}


def test_on_open_runs_once_and_interval_respects_the_clock(tmp_path) -> None:
    mirror = tmp_path / "mirror"
    fs = _Fs(mirror)
    opened = upsert_rule(mirror, path="notes", kind="directory", when="on-open")
    upsert_rule(mirror, path="manual.md", kind="file", when="manual")
    waiting = upsert_rule(
        mirror,
        path="logs",
        kind="directory",
        when="interval",
        interval_minutes=15,
    )
    record_result(mirror, waiting.id, status="ok", output="Copied.")
    now = datetime.now(UTC)
    schedule = SyncSchedule(fs, "/lab/nve", clock=lambda: now)
    assert schedule.tick() == [opened.id]
    assert schedule.tick() == []
    assert fs.calls == ["/lab/nve/notes"]

    later = SyncSchedule(fs, "/lab/nve", clock=lambda: now + timedelta(minutes=15))
    later.skip_on_open(opened.id)
    assert later.tick() == [waiting.id]


def test_a_busy_mirror_skips_the_tick(tmp_path) -> None:
    mirror = tmp_path / "mirror"
    fs = _Fs(mirror)
    rule = upsert_rule(mirror, path="notes", kind="directory", when="on-open")
    schedule = SyncSchedule(fs, "/lab/nve")
    with exclusive_transfer(mirror):
        assert schedule.tick() == []
    assert schedule.tick() == [rule.id]
    assert fs.calls == ["/lab/nve/notes"]


def test_linking_a_remote_root_starts_the_schedule(tmp_path, monkeypatch) -> None:
    started: list[str] = []

    def record(fs, root: str):
        started.append(root)
        return SimpleNamespace()

    monkeypatch.setattr("molab.server.sync_schedule.ensure_sync_schedule", record)
    fs = CachedRemoteFileSystem(object(), mirror_root=tmp_path / "mirror")
    fs.prepare = lambda *_args, **_kwargs: []  # type: ignore[method-assign]
    _ensure_remote_ready(SimpleNamespace(fs=fs, root="/remote/lab"))
    _ensure_remote_ready(SimpleNamespace(fs=object(), root="/local"))
    assert started == ["/remote/lab"]


def test_server_shutdown_stops_the_schedule(tmp_path) -> None:
    fs = _Fs(tmp_path / "mirror")
    upsert_rule(fs.mirror_root, path="note.md", kind="file", when="manual")
    schedule = ensure_sync_schedule(fs, "/lab/nve")
    try:
        app = create_app(serve_static=False)
        with TestClient(app):
            assert not schedule.stopped
        assert schedule.stopped
    finally:
        stop_sync_schedules()
