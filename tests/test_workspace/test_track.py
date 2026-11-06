"""``molab.track()`` for plain scripts and child processes (D94).

``track`` picks, in order: the current execution; an attached tracker when
``MOLAB_EXECUTION_DIR`` names a live attempt; a live attempt of a run it
opens when *project* / *experiment* are given inside a workspace; otherwise
an offline directory. A non-owner never writes ``execution.json``: it stages
files, and the owner registers them at seal.
"""

from __future__ import annotations

import contextvars
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pytest

import molab
from molab.workspace import Workspace, tracking
from molab.workspace.asset_repository import assets_produced_by
from molab.workspace.domain import ExecutionOrigin, ExecutionStatus
from molab.workspace.tracking import (
    MANIFEST,
    STAGED_DIR,
    TRACK_DIR,
    TRACK_RECORD,
    AttachedTracker,
    OfflineTracker,
    StagedFile,
    current,
    print,
)

T0 = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_process_tracker(monkeypatch):
    """Each test starts and ends with no process-wide tracker and no attach env."""
    monkeypatch.delenv(tracking.EXECUTION_DIR_ENV, raising=False)
    monkeypatch.delenv(tracking.TASK_ENV, raising=False)
    monkeypatch.delenv(tracking.STDIO_CAPTURED_ENV, raising=False)
    monkeypatch.setattr(tracking, "_PROCESS", None)
    yield
    leftover = tracking._PROCESS
    if isinstance(leftover, tracking._StagingTracker):
        leftover.close()
    monkeypatch.setattr(tracking, "_PROCESS", None)


def _in_fresh_context(fn, *args: object, **kwargs: object):
    """Run *fn* where no execution is current (a child process's view)."""
    return contextvars.Context().run(fn, *args, **kwargs)


def _wal_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestSurface:
    def test_track_is_exported(self) -> None:
        assert molab.track is tracking.track
        assert "track" in molab.__all__

    def test_track_dir_is_under_work(self) -> None:
        assert TRACK_DIR.as_posix() == "work/_molab"

    def test_every_tracker_is_a_tracker(self, run, tmp_path) -> None:
        with run.start() as ctx:
            assert isinstance(ctx, tracking.Tracker)
            attached = AttachedTracker(ctx.execution_dir)
            assert isinstance(attached, tracking.Tracker)
            attached.close()
        offline = OfflineTracker(tmp_path / "off")
        assert isinstance(offline, tracking.Tracker)
        offline.close()


class TestDispatch:
    def test_case_1_inside_an_execution_returns_it(self, run) -> None:
        with run.start() as ctx:
            assert molab.track() is ctx
            with molab.track() as same:
                assert same is ctx
            # The borrowed ``with`` ended nothing: still current, still running.
            assert current() is ctx
            assert run.executions[-1].status is ExecutionStatus.RUNNING
        assert run.executions[-1].status is ExecutionStatus.SUCCEEDED

    def test_entering_where_it_is_not_current_still_raises(self, run) -> None:
        with run.start() as ctx, pytest.raises(RuntimeError, match="twice"):
            _in_fresh_context(ctx.__enter__)

    def test_case_2_env_attaches_and_with_is_a_no_op(self, run, monkeypatch) -> None:
        with run.start() as ctx:
            monkeypatch.setenv(tracking.EXECUTION_DIR_ENV, str(ctx.execution_dir))
            monkeypatch.setenv(tracking.TASK_ENV, "train")

            def child() -> tracking.Tracker:
                with molab.track() as tracker:
                    pass
                return tracker

            tracker = _in_fresh_context(child)
            assert isinstance(tracker, AttachedTracker)
            assert tracker.task == "train"
            # Bound for the process: a fresh context sees it too.
            assert _in_fresh_context(current) is tracker
            assert _in_fresh_context(molab.track) is tracker
            tracker.close()
            assert _in_fresh_context(current) is None

    def test_case_3_opens_a_run_and_seals_on_with_exit(self, tmp_path, monkeypatch, capsys) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        (tmp_path / "lab" / "scripts").mkdir()
        monkeypatch.chdir(tmp_path / "lab" / "scripts")

        with molab.track(project="p", experiment="e", params={"seed": 1}) as t:
            assert current() is t
            print("hello")
            t.metrics.scalar("loss", 1.0, 0)
        capsys.readouterr()

        run = ws.get_project("p").get_experiment("e").get_run("seed=1")
        (record,) = run.executions
        assert record.status is ExecutionStatus.SUCCEEDED
        assert record.sealed
        assert (run.execution_dir("e01") / "stdout.log").read_text(encoding="utf-8") == "hello\n"
        wal = run.execution_dir("e01") / "metrics.mlp.jsonl"
        assert wal.is_file()
        assert _wal_records(wal)[0]["k"] == "loss"
        assert assets_produced_by(ws, "e01") == []
        assert current() is None

    def test_case_3_without_with_is_sealed_at_exit(self, tmp_path, monkeypatch) -> None:
        ws = Workspace(tmp_path / "lab", name="lab")
        ws.materialize()
        monkeypatch.chdir(tmp_path / "lab")
        t = molab.track(project="p", experiment="e", params={"seed": 2})
        run = ws.get_project("p").get_experiment("e").get_run("seed=2")
        assert run.executions[-1].status is ExecutionStatus.RUNNING
        # A script ended by an uncaught exception leaves it in ``sys.last_exc``.
        monkeypatch.setattr(sys, "last_exc", RuntimeError("boom"), raising=False)
        t._seal_at_exit()
        record = run.executions[-1]
        assert record.status is ExecutionStatus.FAILED
        assert record.error is not None and record.error["type"] == "RuntimeError"

    def test_case_4_outside_a_workspace_writes_the_offline_layout(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with molab.track(project="p", experiment="e") as t:
            assert isinstance(t, OfflineTracker)
            assert current() is t
            print("offline line")
            t.metrics.scalar("loss", 2.0, 3)
            staged = t.register({"a": 1}, title="result.json")
        capsys.readouterr()

        root = tmp_path / "molab-track"
        assert t.execution_dir == root
        assert (root / "stdout.log").read_text(encoding="utf-8") == "offline line\n"
        (record,) = _wal_records(root / "metrics.mlp.jsonl")
        assert record["k"] == "loss" and "tags" not in record
        assert staged.path.startswith("work/_molab/staged/")
        assert json.loads((root / staged.staged).read_text(encoding="utf-8")) == {"a": 1}
        (line,) = (root / MANIFEST).read_text(encoding="utf-8").splitlines()
        assert StagedFile.from_line(line) == staged
        meta = json.loads((root / TRACK_RECORD).read_text(encoding="utf-8"))
        assert meta["started_at"] and meta["finished_at"]
        assert {"host", "pid", "argv", "python", "cwd"} <= set(meta)
        assert current() is None

    def test_offline_dir_argument(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        t = molab.track(tmp_path / "here")
        assert isinstance(t, OfflineTracker)
        assert t.execution_dir == tmp_path / "here"
        t.close()
        assert json.loads((tmp_path / "here" / TRACK_RECORD).read_text())["finished_at"]

    def test_half_a_run_address_is_refused(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="both"):
            molab.track(project="p")


class TestAttached:
    def test_staged_files_are_registered_by_the_owner_at_seal(self, run) -> None:
        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir, task="fit")
            child.write_stdio("stdout", "from child\n")
            child.metrics.scalar("loss", 0.25, 7)
            source = ctx.execution_dir.parent / "outside.txt"
            source.write_text("bytes", encoding="utf-8")
            staged = child.register(source, title="outside.txt", tags={"k": "v"})
            assert assets_produced_by(run.experiment.project.workspace, ctx.id) == []
            child.close()

        record = run.executions[-1]
        produced = assets_produced_by(run.experiment.project.workspace, record.id)
        folded = next(asset for asset in produced if asset.title == "outside.txt")
        assert isinstance(folded.origin, ExecutionOrigin)
        assert folded.origin.task == "fit"
        assert folded.tags["staged_by"] == "child"
        assert folded.tags["k"] == "v"
        assert (ctx.execution_dir / staged.staged).read_text() == "bytes"
        assert not any(asset.title == "metrics.mlp.jsonl" for asset in produced)
        (wal,) = _wal_records(ctx.execution_dir / "metrics.mlp.jsonl")
        assert wal["tags"] == {"task": "fit"}
        assert (ctx.execution_dir / "stdout.log").read_text() == "from child\n"
        stdout = next(ev for ev in record.evidence if ev.kind == "stdout")
        assert stdout.size == len("from child\n")

    def test_a_bad_entry_is_logged_and_the_attempt_still_succeeds(self, run) -> None:
        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir)
            child.register(b"x", title="good.bin")
            with (ctx.execution_dir / MANIFEST).open("a", encoding="utf-8") as fh:
                fh.write("not json\n")
                fh.write(
                    json.dumps({"staged": f"{STAGED_DIR}/9-gone.bin", "name": "gone.bin"}) + "\n"
                )
            child.close()
        record = run.executions[-1]
        assert record.status is ExecutionStatus.SUCCEEDED
        produced = assets_produced_by(run.experiment.project.workspace, record.id)
        assert [asset.title for asset in produced] == ["good.bin"]
        log = (ctx.execution_dir / "run.log").read_text()
        assert f"{MANIFEST}:2 not recorded" in log
        assert f"{MANIFEST}:3 not recorded" in log

    def test_a_staged_name_is_refused_twice(self, run) -> None:
        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir)
            child.register(b"1", title="a.bin")
            with pytest.raises(ValueError, match="already staged"):
                child.register(b"2", title="a.bin")
            with pytest.raises(ValueError, match="reserved"):
                child.register(b"3", title="_molab/x")
            child.close()

    def test_image_ref_points_at_the_staged_path(self, run) -> None:
        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir)
            record = child.metrics.image("rdf", b"\x89PNG", name="rdf.png", step=1)
            assert str(record["v"]["path"]).startswith("work/_molab/staged/")
            child.close()
        produced = assets_produced_by(run.experiment.project.workspace, run.executions[-1].id)
        image = next(asset for asset in produced if asset.title == "rdf.png")
        assert image.media_type == "image/png"
        (on_disk,) = _wal_records(ctx.execution_dir / "metrics.mlp.jsonl")
        assert on_disk["v"]["path"].startswith("work/_molab/staged/")


class TestSealGuard:
    def test_attaching_to_a_sealed_attempt_raises(self, run) -> None:
        with run.start() as ctx:
            pass
        with pytest.raises(RuntimeError, match="sealed"):
            AttachedTracker(ctx.execution_dir)

    def test_attaching_to_a_directory_without_a_record_raises(self, tmp_path) -> None:
        with pytest.raises(RuntimeError, match=r"execution\.json"):
            AttachedTracker(tmp_path)

    def test_a_write_after_seal_is_dropped_with_one_warning(self, run, monkeypatch) -> None:
        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir)
            child.write_stdio("stdout", "early\n")
        monkeypatch.setattr(tracking, "SEAL_CHECK_SECONDS", 0.0)
        tracking._bind_process(child)
        stdout = ctx.execution_dir / "stdout.log"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            child.write_stdio("stdout", "late\n")
            print("late print")
            child.metrics.scalar("loss", 1.0, 1)
        assert [w.category for w in caught] == [RuntimeWarning]
        assert stdout.read_text() == "early\n"
        assert not (ctx.execution_dir / "metrics.mlp.jsonl").exists()
        with pytest.raises(RuntimeError, match="sealed"):
            child.register(b"x", title="late.bin")
        child.close()

    def test_a_write_inside_the_check_interval_is_not_re_read(self, run, monkeypatch) -> None:
        calls: list[Path] = []
        real = tracking._read_sealed

        def counting(path: Path) -> str | None:
            calls.append(path)
            return real(path)

        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir)
            monkeypatch.setattr(tracking, "_read_sealed", counting)
            for _ in range(5):
                child.write_stdio("stdout", "x\n")
            child.close()
        assert calls == []


class TestCapturedStdio:
    def test_a_captured_child_copies_no_print(self, run, monkeypatch) -> None:
        monkeypatch.setenv(tracking.STDIO_CAPTURED_ENV, "1")
        with run.start() as ctx:
            child = _in_fresh_context(AttachedTracker, ctx.execution_dir)
            child.write_stdio("stdout", "dup\n")
            child.close()
        assert not (ctx.execution_dir / "stdout.log").exists()


class TestChildEnv:
    def test_execution_context_child_env(self, run) -> None:
        with run.start() as ctx:
            env = ctx.child_env()
            assert env == {
                tracking.EXECUTION_DIR_ENV: str(ctx.execution_dir.absolute()),
                tracking.TASK_ENV: "",
            }
            with tracking.task_scope("md"):
                assert ctx.child_env()[tracking.TASK_ENV] == "md"


class TestOfflineAdopt:
    def _offline(self, root: Path) -> Path:
        tracker = OfflineTracker(root)
        tracker.write_stdio("stdout", "trained\n")
        tracker.write_stdio("stderr", "warned\n")
        tracker.metrics.scalar("loss", 0.1, 10)
        source = root.parent / "model.pt"
        source.write_bytes(b"weights")
        tracker.register(source, title="model.pt", tags={"epoch": "10"})
        tracker.close()
        return root

    def test_tracked_directory_becomes_a_sealed_attempt(self, run, tmp_path) -> None:
        root = self._offline(tmp_path / "track")
        layout = tracking.read_tracked(root)

        record = run.adopt_execution(started_at=T0, finished_at=T1, tracked=root)

        attempt = run.execution_dir(record.id)
        assert record.sealed and record.status is ExecutionStatus.SUCCEEDED
        assert (attempt / "stdout.log").read_text() == "trained\n"
        assert (attempt / "stderr.log").read_text() == "warned\n"
        assert (attempt / "metrics.mlp.jsonl").is_file()
        produced = assets_produced_by(run.experiment.project.workspace, record.id)
        model = next(asset for asset in produced if asset.title == "model.pt")
        assert model.tags == {"epoch": "10"}
        assert model.content.size == len(b"weights")
        payload = run.experiment.project.workspace.assets_at(model.scope).payload_path(model.id)
        assert Path(payload).read_bytes() == b"weights"
        assert not (root / layout.staged[0].staged).exists()
        kinds = {ev.kind for ev in record.evidence}
        assert {"stdout", "stderr"} <= kinds
        assert (root / TRACK_RECORD).is_file()
        assert not (root / "stdout.log").exists()
        on_disk = json.loads((attempt / "execution.json").read_text())
        assert "artifacts" not in on_disk

    def test_a_staged_metrics_name_coexists_with_the_wal(self, run, tmp_path) -> None:
        root = self._offline(tmp_path / "track")
        clash = OfflineTracker(root)
        clash.register(b"{}", title="metrics.mlp.jsonl")
        clash.close()

        record = run.adopt_execution(started_at=T0, finished_at=T1, tracked=root)

        attempt = run.execution_dir(record.id)
        assert _wal_records(attempt / "metrics.mlp.jsonl")[0]["k"] == "loss"
        produced = assets_produced_by(run.experiment.project.workspace, record.id)
        named = [asset for asset in produced if asset.title == "metrics.mlp.jsonl"]
        assert len(named) == 1
        payload = run.experiment.project.workspace.assets_at(named[0].scope).payload_path(
            named[0].id
        )
        assert Path(payload).read_bytes() == b"{}"

    def test_a_rerun_offline_directory_keeps_its_first_start(self, tmp_path) -> None:
        first = OfflineTracker(tmp_path / "t")
        first.close()
        started = json.loads((tmp_path / "t" / TRACK_RECORD).read_text())["started_at"]
        second = OfflineTracker(tmp_path / "t")
        record = json.loads((tmp_path / "t" / TRACK_RECORD).read_text())
        assert record["started_at"] == started
        assert record["finished_at"] is None
        second.close()
